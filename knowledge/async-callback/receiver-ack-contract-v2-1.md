# Receiver acknowledgement and processing SLA v2.1

An HTTP 202 from the receiver proves durable acceptance into its queue only. It does not by itself prove that the receiver completed business processing.

Check the receiver's current state for the same `event_id` and `delivery_version`. `PROCESSED` is sufficient to prove completion even before the SLA deadline, provided the current receiver observation is correlated to that same event and delivery version.

SLA only sets the handling direction for a same-event receiver that remains `QUEUED`: before the trusted deadline, continue observing; at or after the deadline, contact the receiver operator to investigate. An overdue `QUEUED` state does not by itself prove business failure or event loss.

HTTP 202 alone proves acceptance only; without current same-event receiver evidence, the processing state is `UNKNOWN`. Do not infer the target event's state from elapsed time, a different event, an order snapshot, or historical advice. Never resend automatically.
