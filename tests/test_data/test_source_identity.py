"""Offline company-identity regressions for public fallback evidence."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from primr.data import fallback_sources as fb
from primr.data import hiring_signals as hs
from primr.data.first_party_url import belongs_to_website, website_links
from primr.data.hiring_identity import (
    discover_verified_ats,
    verify_guessed_board,
    verify_search_postings,
)
from primr.data.hiring_signals import Posting
from primr.utils.model_policy import disable_model_calls


def _response(value):
    return 200, json.dumps(value).encode(), None


def _website_claim(url, *, rank="normal", qualifiers=None):
    return {
        "rank": rank,
        "qualifiers": qualifiers or {},
        "mainsnak": {"snaktype": "value", "datavalue": {"value": url}},
    }


def _wiki_http(claims):
    def get(url, *, params, **kwargs):
        if params.get("list") == "search":
            return _response(
                {
                    "query": {
                        "search": [{"title": "Example (musician)"}, {"title": "Example Holdings"}]
                    }
                }
            )
        if params.get("prop") == "pageprops":
            return _response(
                {
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Example (musician)",
                                "pageprops": {"wikibase_item": "Q1"},
                            },
                            "2": {
                                "title": "Example Holdings",
                                "pageprops": {"wikibase_item": "Q2"},
                            },
                        }
                    }
                }
            )
        if params.get("action") == "wbgetentities":
            assert url == "https://www.wikidata.org/w/api.php"
            assert params["ids"] == "Q1|Q2"
            return _response(
                {
                    "entities": {
                        "Q1": {"claims": {"P856": [_website_claim("https://artist.example")]}},
                        "Q2": {"claims": {"P856": claims}},
                    }
                }
            )
        if params.get("prop") == "extracts":
            assert params["titles"] == "Example Holdings"
            return _response(
                {
                    "query": {
                        "pages": {
                            "2": {
                                "pageid": 2,
                                "extract": "Example Holdings provides company services. " * 40,
                            }
                        }
                    }
                }
            )
        raise AssertionError(params)

    return get


def test_wikipedia_skips_same_name_musician_and_collects_site_match():
    with patch.object(
        fb, "_http_get", side_effect=_wiki_http([_website_claim("https://www.acme.example/about")])
    ) as http:
        pages = fb.fetch_wikipedia_content("Example", website="https://acme.example")
    assert len(pages) == 1
    assert pages[0].title == "Example Holdings"
    assert pages[0].metadata["identity"] == "verified"
    assert http.call_count == 4


@pytest.mark.parametrize(
    "claims",
    [
        [],
        [_website_claim("https://unrelated.example")],
        [_website_claim("https://acme.example.evil.example")],
        [_website_claim("https://acme.example@evil.example")],
        [_website_claim("https://acme.example", rank="deprecated")],
        [_website_claim("https://acme.example", qualifiers={"P582": [{}]})],
        [
            _website_claim("https://acme.example"),
            _website_claim("https://new.example", rank="preferred"),
        ],
    ],
)
def test_wikipedia_requires_current_official_website(claims):
    with patch.object(fb, "_http_get", side_effect=_wiki_http(claims)) as http:
        assert fb.fetch_wikipedia_content("Example", website="https://acme.example") == []
    assert http.call_count == 3


def test_wikipedia_without_target_never_guesses():
    with patch.object(fb, "_http_get") as http:
        assert fb.find_wikipedia_title("Example") is None
        assert fb.fetch_wikipedia_content("Example") == []
    http.assert_not_called()


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"query": {"search": null}}'])
def test_wikipedia_bad_responses_fail_closed(body):
    with patch.object(fb, "_http_get", return_value=(200, body, None)):
        assert fb.find_wikipedia_title("Example", website="https://acme.example") is None


@pytest.mark.parametrize("value", [[], "invalid", {"pageprops": []}])
def test_wikipedia_malformed_page_properties_fail_closed(value):
    responses = [
        _response({"query": {"search": [{"title": "Example"}]}}),
        _response({"query": {"pages": {"1": value}}}),
    ]
    with patch.object(fb, "_http_get", side_effect=responses):
        assert fb.find_wikipedia_title("Example", website="https://acme.example") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://acme.example.evil.example",
        "https://evilacme.example",
        "https://acme.example@evil.example",
        "https://evil.example/?next=https://acme.example",
        "https://evil.example/#https://acme.example",
        "javascript:https://acme.example",
        "mailto:hello@acme.example",
        "https://[",
        "acme.example",
    ],
)
def test_site_identity_rejects_lookalikes_and_embedded_urls(url):
    assert not belongs_to_website(url, "https://acme.example")
    assert not any(
        belongs_to_website(link, "https://acme.example")
        for link in website_links(f'<a href="{url}">Company</a>', "https://jobs.example")
    )


@pytest.mark.parametrize(
    "url", ["https://www.acme.example./about", "https://careers.acme.example:8443/"]
)
def test_site_identity_preserves_normalized_company_links(url):
    assert belongs_to_website(url, "https://acme.example")


def test_identity_link_parser_ignores_scripts_comments_and_bare_name():
    content = """<script>var company = 'https://acme.example';</script>
    <!-- https://acme.example --><style>/* https://acme.example */</style>
    Acme Example <a href="https://other.example/?next=https://acme.example">Company</a>"""
    assert not any(
        belongs_to_website(link, "https://acme.example")
        for link in website_links(content, "https://jobs.example")
    )
    assert website_links(
        '<iframe src="https://jobs.lever.co/acme"></iframe>', "https://acme.example"
    ) == ["https://jobs.lever.co/acme"]


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
def test_hostname_boundary_does_not_accept_suffix_spoof(label):
    assert not belongs_to_website(f"https://acme.example.{label}.example", "https://acme.example")


def _job_schema(url, employer="https://acme.example", **extra):
    job = {
        "@type": "JobPosting",
        "url": url,
        "hiringOrganization": {"@type": "Organization", "sameAs": employer},
        **extra,
    }
    return '<script type="application/ld+json">' + json.dumps(job) + "</script>"


def test_product_customer_and_tool_links_do_not_verify_an_unrelated_board():
    for body in (
        "OtherCo hires engineers who use https://acme.example software.",
        '<p>OtherCo hires engineers who use <a href="https://acme.example">Acme software</a>.</p>',
        '<p>Our customer <a href="https://acme.example">Acme</a> relies on us.</p>',
    ):
        posts = [
            Posting(
                url=f"https://job-boards.greenhouse.io/other/jobs/{i}", title="Engineer", body=body
            )
            for i in range(3)
        ]
        http = Mock(return_value=(200, body.encode(), None))
        assert verify_guessed_board(posts, "https://acme.example", http_get=http, timeout=1) == []
        assert all(post.identity == "unverified" for post in posts)
        assert http.call_count == 3


def test_explicit_board_homepage_links_whole_tenant():
    posts = [
        Posting(url=f"https://job-boards.greenhouse.io/acme/jobs/{i}", title="Engineer")
        for i in range(3)
    ]
    http = Mock(
        return_value=(
            200,
            b'<header><a href="https://acme.example" aria-label="Company website">Acme</a></header>',
            None,
        )
    )
    assert verify_guessed_board(posts, "https://acme.example", http_get=http, timeout=1) == posts
    assert http.call_args.args[0] == "https://job-boards.greenhouse.io/acme"
    assert all(
        post.identity_evidence == "board_company_homepage:https://acme.example" for post in posts
    )


def test_posting_employer_metadata_does_not_promote_other_jobs_on_mixed_board():
    posts = [Posting(url=f"https://jobs.lever.co/shared/{i}", title="Engineer") for i in range(3)]

    def get(url, **kwargs):
        if url == posts[0].url:
            return 200, _job_schema(url).encode(), None
        return 200, _job_schema(url, employer="https://other.example").encode(), None

    http = Mock(side_effect=get)
    assert verify_guessed_board(posts, "https://acme.example", http_get=http, timeout=1) == [
        posts[0]
    ]
    assert posts[0].identity_evidence == "jobposting_hiring_organization:https://acme.example"
    assert posts[1].identity == posts[2].identity == "unverified"
    assert http.call_count == 3


def test_unrelated_first_board_does_not_mask_legitimate_same_provider_candidate():
    def fetch(slug):
        url = f"https://jobs.lever.co/{slug}/1"
        employer = "https://acme.example" if slug == "acme-hq" else "https://other.example"
        return [Posting(url=url, title="Engineer", body=_job_schema(url, employer))]

    http = Mock(return_value=(404, None, None))
    posts, source = discover_verified_ats(
        ["acme", "acme-hq"],
        "https://acme.example",
        providers=[("lever", fetch)],
        http_get=http,
        timeout=1,
        max_workers=2,
    )
    assert source == "lever"
    assert len(posts) == 1
    assert "/acme-hq/" in posts[0].url


def test_search_result_cannot_use_an_aggregator_index_backlink():
    post = Posting(url="https://jobs.example/jobs/view/123", title="Engineer")

    def get(url, **kwargs):
        if url == "https://jobs.example/jobs":
            return 200, b'<a href="https://acme.example">Featured employer</a>', None
        return 200, b'<a href="https://other.example">Actual employer</a>', None

    http = Mock(side_effect=get)
    assert verify_search_postings([post], "https://acme.example", http_get=http, timeout=1) == []
    assert http.call_args.args[0] == post.url
    assert http.call_count == 1


def test_search_identity_budget_stops_further_fetches():
    posts = [Posting(url=f"https://jobs.example/view/{i}", title="Engineer") for i in range(3)]
    http = Mock(return_value=(404, None, None))
    with patch("primr.data.hiring_identity.time.monotonic", side_effect=[0, 0, 21]):
        assert verify_search_postings(posts, "https://acme.example", http_get=http, timeout=6) == []
    assert http.call_count == 1


def _no_models():
    return patch.object(
        hs.stage_routing,
        "resolve_stage_model",
        return_value=SimpleNamespace(
            execution_mode="unavailable",
            model_name=None,
            log_metadata=dict,
        ),
    )


def test_first_party_board_link_precedes_unrelated_guessed_tenant(tmp_path):
    posts = [
        Posting(
            url="https://job-boards.greenhouse.io/acme-hq/jobs/1",
            title="Engineer",
            source="greenhouse",
        )
    ]
    corpus = {
        "https://acme.example/careers": '<a href="https://job-boards.greenhouse.io/acme-hq">Open roles</a>'
    }
    with (
        patch.object(hs, "_fetch_greenhouse", return_value=posts) as fetch,
        patch.object(hs, "_discover_via_ats") as guessed,
        patch.object(hs, "_http_get", return_value=(404, None, None)),
        _no_models(),
        disable_model_calls(),
    ):
        signals = hs.gather_hiring_signals(
            "Acme", "https://acme.example", corpus=corpus, working_folder=str(tmp_path)
        )
    assert signals.postings_found == 1
    guessed.assert_not_called()
    fetch.assert_called_once_with("acme-hq")
    index = json.loads((tmp_path / "_hiring" / "postings_index.json").read_text())
    assert index[0]["identity"] == "verified"
    assert index[0]["identity_evidence"] == "first_party_careers:https://acme.example/careers"


def test_unrelated_corpus_does_not_establish_careers_or_workday_identity():
    corpus = {"https://other.example/careers": "https://other.wd5.myworkdayjobs.com/External/job/1"}
    assert "https://other.example/careers" not in hs._careers_url_candidates(
        "https://acme.example", corpus
    )
    with (
        patch.object(hs, "_http_get", return_value=(404, None, None)),
        patch.object(hs, "_ATS_PROVIDERS", []),
        patch.object(hs, "_workday_fetch_one") as workday,
        patch.object(hs, "_discover_via_web_search", return_value=[]),
        disable_model_calls(),
    ):
        signals = hs.gather_hiring_signals("Acme", "https://acme.example", corpus=corpus)
    assert signals.postings_found == 0
    workday.assert_not_called()


def test_same_name_wiki_and_ats_yield_zero_verified_evidence():
    unrelated = Posting(
        url="https://job-boards.greenhouse.io/example/jobs/1",
        title="Engineer",
        source="greenhouse",
        body="Other company",
    )
    with (
        patch.object(
            fb, "_http_get", side_effect=_wiki_http([_website_claim("https://other.example")])
        ),
        patch.object(
            hs, "_http_get", return_value=(200, b'<a href="https://other.example">Other</a>', None)
        ),
        patch.object(hs, "_ATS_PROVIDERS", [("greenhouse", lambda slug: [unrelated])]),
        patch.object(hs, "_discover_via_web_search", return_value=[unrelated]),
        disable_model_calls(),
    ):
        pages = fb.fetch_wikipedia_content("Example", website="https://example.com")
        signals = hs.gather_hiring_signals("Example", "https://example.com")
    assert pages == []
    assert signals.postings_found == 0
    assert unrelated.identity == "unverified"


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io.evil.example/acme",
        "https://jobs.lever.co.evil.example/acme",
        "https://acme.wd5.myworkdayjobs.com.evil.example/External",
    ],
)
def test_ats_referrals_require_exact_provider_hosts(url):
    with (
        patch.object(hs, "_fetch_greenhouse") as greenhouse,
        patch.object(hs, "_fetch_lever") as lever,
        patch.object(hs, "_workday_fetch_one") as workday,
    ):
        assert hs._detect_ats_redirect(url) is None
    greenhouse.assert_not_called()
    lever.assert_not_called()
    workday.assert_not_called()


@pytest.mark.parametrize(
    "malformed_claim",
    [
        {"rank": "unknown", "mainsnak": {"datavalue": {"value": "https://acme.example"}}},
        {"qualifiers": [], "mainsnak": {"datavalue": {"value": "https://acme.example"}}},
        {"mainsnak": {"datavalue": []}},
        {"mainsnak": {"snaktype": "novalue", "datavalue": {"value": "https://acme.example"}}},
    ],
)
def test_wikipedia_malformed_official_claims_fail_closed(malformed_claim):
    with patch.object(fb, "_http_get", side_effect=_wiki_http([malformed_claim])):
        assert fb.fetch_wikipedia_content("Example", website="https://acme.example") == []


@pytest.mark.parametrize("kind", ["NotJobPosting", "Organization", "Product"])
def test_only_actual_jobposting_employer_metadata_links_identity(kind):
    post = Posting(url="https://jobs.example/123", title="Engineer")
    body = _job_schema(post.url, **{"@type": kind})
    http = Mock(return_value=(200, body.encode(), None))
    assert verify_search_postings([post], "https://acme.example", http_get=http, timeout=1) == []


def test_related_posting_schema_cannot_verify_a_different_role():
    post = Posting(url="https://jobs.example/123", title="Engineer")
    body = _job_schema("https://jobs.example/456")
    http = Mock(return_value=(200, body.encode(), None))
    assert verify_search_postings([post], "https://acme.example", http_get=http, timeout=1) == []


def test_json_ld_graph_and_organization_reference_remain_useful():
    post = Posting(url="https://jobs.example/123", title="Engineer")
    graph = {
        "@graph": [
            {"@type": "JobPosting", "@id": "#job", "hiringOrganization": {"@id": "#employer"}},
            {"@type": "Organization", "@id": "#employer", "url": "https://acme.example"},
        ]
    }
    body = '<script type="application/ld+json">' + json.dumps(graph) + "</script>"
    http = Mock(return_value=(200, body.encode(), None))
    assert verify_search_postings([post], "https://acme.example", http_get=http, timeout=1) == [
        post
    ]


def test_wikipedia_preserves_search_rank_across_unordered_pages_and_redirects():
    responses = [
        _response(
            {"query": {"search": [{"title": "Example Parent"}, {"title": "Example Subsidiary"}]}}
        ),
        _response(
            {
                "query": {
                    "redirects": [{"from": "Example Parent", "to": "Example Holdings"}],
                    "pages": {
                        "2": {"title": "Example Subsidiary", "pageprops": {"wikibase_item": "Q2"}},
                        "1": {"title": "Example Holdings", "pageprops": {"wikibase_item": "Q1"}},
                    },
                }
            }
        ),
        _response(
            {
                "entities": {
                    item: {"claims": {"P856": [_website_claim("https://acme.example")]}}
                    for item in ("Q1", "Q2")
                }
            }
        ),
    ]
    with patch.object(fb, "_http_get", side_effect=responses):
        assert (
            fb.find_wikipedia_title("Example", website="https://acme.example") == "Example Holdings"
        )


def test_posting_identity_preserves_job_ids_in_query_strings():
    post = Posting(url="https://jobs.example/careers?gh_jid=123", title="Engineer")
    body = _job_schema("https://jobs.example/careers?gh_jid=456")
    http = Mock(return_value=(200, body.encode(), None))
    assert verify_search_postings([post], "https://acme.example", http_get=http, timeout=1) == []


def test_role_description_company_website_label_is_not_board_navigation():
    post = Posting(url="https://jobs.lever.co/other/123", title="Engineer")
    body = '<article><a rel="home" href="https://acme.example">Company website</a></article>'
    http = Mock(return_value=(200, body.encode(), None))
    assert verify_guessed_board([post], "https://acme.example", http_get=http, timeout=1) == []
