"""
Message Queue Abstraction - Queue backends for job orchestration.

This module provides message queue abstraction across different cloud providers:
- SQS (AWS)
- Service Bus (Azure)
- Pub/Sub (GCP)
- InMemory (testing)

Key features:
- Queue protocol (enqueue, dequeue)
- Message includes job_id, deployment, inputs, attempt
- FIFO ordering support where available

Requirements: 5.2, 6.2, 7.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
import time
from typing import Any, Protocol, runtime_checkable
import uuid


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class QueueMessage:
    """Message for job queue."""

    job_id: str
    deployment: str
    api_key_hash: str
    inputs: dict[str, Any]
    enqueued_at: str
    attempt: int = 1
    message_id: str = ""
    receipt_handle: str = ""  # For message deletion after processing

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "deployment": self.deployment,
            "api_key_hash": self.api_key_hash,
            "inputs": self.inputs,
            "enqueued_at": self.enqueued_at,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], message_id: str = "", receipt_handle: str = ""
    ) -> QueueMessage:
        return cls(
            job_id=data.get("job_id", ""),
            deployment=data.get("deployment", ""),
            api_key_hash=data.get("api_key_hash", ""),
            inputs=data.get("inputs", {}),
            enqueued_at=data.get("enqueued_at", ""),
            attempt=data.get("attempt", 1),
            message_id=message_id,
            receipt_handle=receipt_handle,
        )


@runtime_checkable
class Queue(Protocol):
    """Protocol for message queue backends."""

    def enqueue(self, message: QueueMessage) -> str:
        """
        Enqueue a message.

        Args:
            message: Message to enqueue

        Returns:
            Message ID
        """
        ...

    def dequeue(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[QueueMessage]:
        """
        Dequeue messages.

        Args:
            max_messages: Maximum number of messages to receive
            visibility_timeout: Time in seconds before message becomes visible again

        Returns:
            List of messages
        """
        ...

    def delete(self, receipt_handle: str) -> None:
        """
        Delete a message after successful processing.

        Args:
            receipt_handle: Receipt handle from dequeue
        """
        ...


class InMemoryQueue:
    """
    In-memory queue for testing.

    Thread-safe implementation using locks.
    """

    def __init__(self) -> None:
        self._messages: list[QueueMessage] = []
        self._in_flight: dict[
            str, tuple[QueueMessage, float]
        ] = {}  # receipt_handle -> (message, visible_at)
        self._lock = threading.Lock()

    def enqueue(self, message: QueueMessage) -> str:
        """Enqueue a message."""
        with self._lock:
            if not message.message_id:
                message.message_id = str(uuid.uuid4())
            self._messages.append(message)
            return message.message_id

    def dequeue(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[QueueMessage]:
        """Dequeue messages."""
        with self._lock:
            now = time.time()

            # Return messages that have become visible again
            for receipt_handle, (msg, visible_at) in list(self._in_flight.items()):
                if now >= visible_at:
                    self._messages.append(msg)
                    del self._in_flight[receipt_handle]

            # Get available messages
            result = []
            remaining = []

            for msg in self._messages:
                if len(result) < max_messages:
                    receipt_handle = str(uuid.uuid4())
                    msg.receipt_handle = receipt_handle
                    self._in_flight[receipt_handle] = (msg, now + visibility_timeout)
                    result.append(msg)
                else:
                    remaining.append(msg)

            self._messages = remaining
            return result

    def delete(self, receipt_handle: str) -> None:
        """Delete a message after processing."""
        with self._lock:
            if receipt_handle in self._in_flight:
                del self._in_flight[receipt_handle]

    def clear(self) -> None:
        """Clear all messages (for testing)."""
        with self._lock:
            self._messages.clear()
            self._in_flight.clear()

    def size(self) -> int:
        """Get queue size (for testing)."""
        with self._lock:
            return len(self._messages) + len(self._in_flight)


class SQSQueue:
    """
    AWS SQS queue implementation.

    Supports FIFO queues with content-based deduplication.
    """

    def __init__(
        self,
        queue_url: str,
        region: str | None = None,
        client: Any = None,
        is_fifo: bool = True,
    ) -> None:
        """
        Initialize SQS queue.

        Args:
            queue_url: SQS queue URL
            region: AWS region
            client: Optional boto3 SQS client (for testing)
            is_fifo: Whether this is a FIFO queue
        """
        self.queue_url = queue_url
        self.region = region
        self._client = client
        self.is_fifo = is_fifo

    @property
    def client(self) -> Any:
        """Get or create boto3 SQS client."""
        if self._client is None:
            import boto3

            self._client = boto3.client("sqs", region_name=self.region)
        return self._client

    def enqueue(self, message: QueueMessage) -> str:
        """Enqueue a message to SQS."""
        params = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(message.to_dict()),
        }

        if self.is_fifo:
            # Use job_id as deduplication ID and message group
            params["MessageDeduplicationId"] = message.job_id
            params["MessageGroupId"] = message.deployment

        response = self.client.send_message(**params)
        return response["MessageId"]

    def dequeue(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[QueueMessage]:
        """Dequeue messages from SQS."""
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(max_messages, 10),  # SQS max is 10
            VisibilityTimeout=visibility_timeout,
            WaitTimeSeconds=0,  # Short polling for now
        )

        messages = []
        for msg in response.get("Messages", []):
            body = json.loads(msg["Body"])
            messages.append(
                QueueMessage.from_dict(
                    body,
                    message_id=msg["MessageId"],
                    receipt_handle=msg["ReceiptHandle"],
                )
            )

        return messages

    def delete(self, receipt_handle: str) -> None:
        """Delete a message from SQS."""
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )


class ServiceBusQueue:
    """
    Azure Service Bus queue implementation.

    Supports sessions for ordering.
    """

    def __init__(
        self,
        queue_name: str,
        connection_string: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize Service Bus queue.

        Args:
            queue_name: Service Bus queue name
            connection_string: Azure Service Bus connection string
            client: Optional ServiceBusClient (for testing)
        """
        self.queue_name = queue_name
        self.connection_string = connection_string
        self._client = client

    @property
    def client(self) -> Any:
        """Get or create Service Bus client."""
        if self._client is None:
            from azure.servicebus import ServiceBusClient

            self._client = ServiceBusClient.from_connection_string(self.connection_string)
        return self._client

    def enqueue(self, message: QueueMessage) -> str:
        """Enqueue a message to Service Bus."""
        from azure.servicebus import ServiceBusMessage

        with self.client.get_queue_sender(self.queue_name) as sender:
            sb_message = ServiceBusMessage(
                body=json.dumps(message.to_dict()),
                message_id=message.message_id,
                session_id=message.deployment,  # Use deployment for session ordering
            )
            sender.send_messages(sb_message)

        return message.message_id

    def dequeue(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[QueueMessage]:
        """Dequeue messages from Service Bus."""

        messages = []
        with self.client.get_queue_receiver(
            self.queue_name,
            max_wait_time=1,
        ) as receiver:
            for msg in receiver.receive_messages(
                max_message_count=max_messages,
                max_wait_time=1,
            ):
                body = json.loads(str(msg))
                messages.append(
                    QueueMessage.from_dict(
                        body,
                        message_id=msg.message_id,
                        receipt_handle=msg.lock_token,
                    )
                )

        return messages

    def delete(self, receipt_handle: str) -> None:
        """Complete a message in Service Bus."""
        # Note: In Service Bus, messages are completed via the receiver
        # This is a simplified implementation


class PubSubQueue:
    """
    Google Cloud Pub/Sub queue implementation.

    Uses exactly-once delivery where available.
    """

    def __init__(
        self,
        project: str,
        topic_id: str,
        subscription_id: str,
        publisher: Any = None,
        subscriber: Any = None,
    ) -> None:
        """
        Initialize Pub/Sub queue.

        Args:
            project: GCP project ID
            topic_id: Pub/Sub topic ID
            subscription_id: Pub/Sub subscription ID
            publisher: Optional PublisherClient (for testing)
            subscriber: Optional SubscriberClient (for testing)
        """
        self.project = project
        self.topic_id = topic_id
        self.subscription_id = subscription_id
        self._publisher = publisher
        self._subscriber = subscriber

    @property
    def publisher(self) -> Any:
        """Get or create Pub/Sub publisher client."""
        if self._publisher is None:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    @property
    def subscriber(self) -> Any:
        """Get or create Pub/Sub subscriber client."""
        if self._subscriber is None:
            from google.cloud import pubsub_v1

            self._subscriber = pubsub_v1.SubscriberClient()
        return self._subscriber

    @property
    def topic_path(self) -> str:
        """Get full topic path."""
        return f"projects/{self.project}/topics/{self.topic_id}"

    @property
    def subscription_path(self) -> str:
        """Get full subscription path."""
        return f"projects/{self.project}/subscriptions/{self.subscription_id}"

    def enqueue(self, message: QueueMessage) -> str:
        """Publish a message to Pub/Sub."""
        data = json.dumps(message.to_dict()).encode("utf-8")
        future = self.publisher.publish(
            self.topic_path,
            data,
            job_id=message.job_id,
            deployment=message.deployment,
        )
        return future.result()

    def dequeue(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[QueueMessage]:
        """Pull messages from Pub/Sub."""
        response = self.subscriber.pull(
            request={
                "subscription": self.subscription_path,
                "max_messages": max_messages,
            },
            timeout=5,
        )

        messages = []
        for received in response.received_messages:
            body = json.loads(received.message.data.decode("utf-8"))
            messages.append(
                QueueMessage.from_dict(
                    body,
                    message_id=received.message.message_id,
                    receipt_handle=received.ack_id,
                )
            )

        return messages

    def delete(self, receipt_handle: str) -> None:
        """Acknowledge a message in Pub/Sub."""
        self.subscriber.acknowledge(
            request={
                "subscription": self.subscription_path,
                "ack_ids": [receipt_handle],
            }
        )
