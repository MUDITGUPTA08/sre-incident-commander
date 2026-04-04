"""SRE Incident Commander — core environment logic.

Implements five incident scenarios (easy → expert) with mock infrastructure,
state machines, and shaped reward signals. No external dependencies beyond
Python stdlib.
"""

import copy
import uuid
from typing import Any, Dict, List, Optional

from openenv.core.env_server import Environment

try:
    from ..models import SREAction, SREObservation, SREState
except ImportError:
    from models import SREAction, SREObservation, SREState


# ---------------------------------------------------------------------------
# Task configuration constants
# ---------------------------------------------------------------------------

TASK_CONFIGS: Dict[str, Dict[str, Any]] = {
    "easy": {
        "id": "easy",
        "name": "The Traffic Spike",
        "difficulty": "easy",
        "description": (
            "Worker-node CPU is at 92% and the order-processing queue has a "
            "backlog of 500 messages growing at 200/min. Scale workers to "
            "drain the queue before it overflows."
        ),
        "max_attempts": 10,
        "alerts": [
            {
                "severity": "critical",
                "service": "order-processing-queue",
                "message": "SQS queue backlog critical: 500 messages pending",
            },
            {
                "severity": "warning",
                "service": "worker-node",
                "message": "High CPU utilisation: 92%",
            },
        ],
        "services": {
            "api-gateway": {"status": "healthy", "replicas": 3, "cpu": 45.0},
            "worker-node": {
                "status": "degraded",
                "replicas": 2,
                "cpu": 92.0,
                "version": "v1.4.0",
            },
            "order-processing-queue": {
                "status": "backlogged",
                "queue_length": 500,
                "growth_rate": "+200/min",
            },
            "database": {"status": "healthy", "connections": 45},
        },
        "metrics": {
            "cpu_percent": 92.0,
            "memory_percent": 68.0,
            "queue_depth": 500,
            "error_rate_percent": 2.1,
            "latency_p99_ms": 450,
            "db_connections": 45,
        },
        "logs": {
            "worker-node": (
                "[2026-04-05T07:15:42Z] [CRITICAL] container=worker-node-2 reason=OOMKilled exitCode=137 — pod restarted\n"
                "[2026-04-05T07:15:40Z] [ERROR] req_id=q-8821 message processing failed: context deadline exceeded (30s)\n"
                "[2026-04-05T07:15:35Z] [WARN]  worker-node-1 CPU at 92% — kernel throttling cgroup cpu.cfs_quota_us\n"
                "[2026-04-05T07:15:30Z] [WARN]  GC pause 450ms — heap pressure from message backlog in memory\n"
                "[2026-04-05T07:15:00Z] [INFO]  consumer throughput: 100 msg/min per replica (2 replicas = 200 msg/min total)\n"
                "[2026-04-05T07:15:00Z] [INFO]  current replicas: 2 — recommended: scale to 5+ to match inbound rate\n"
                "[2026-04-05T07:14:30Z] [INFO]  autoscaler disabled (manual scaling mode) — operator action required\n"
                "[2026-04-05T07:14:00Z] [ERROR] request queue backing up — consumer lag increasing at 200 msg/min"
            ),
            "order-processing-queue": (
                "[2026-04-05T07:15:45Z] [CRITICAL] queue depth 500/1000 — 50% capacity, overflow in ~2.5 min at current rate\n"
                "[2026-04-05T07:15:30Z] [WARN]  message age (oldest): 12 minutes — SLA breach at 15 min\n"
                "[2026-04-05T07:15:00Z] [WARN]  growth rate: +200 msg/min (inbound) — drain rate: 200 msg/min (2 workers)\n"
                "[2026-04-05T07:15:00Z] [INFO]  net throughput: 0 msg/min (growth = drain) — queue NOT draining\n"
                "[2026-04-05T07:14:30Z] [INFO]  dead letter queue: 0 messages (no poison pills)\n"
                "[2026-04-05T07:14:00Z] [INFO]  queue capacity: 1000 messages — messages dropped on overflow"
            ),
            "api-gateway": (
                "[2026-04-05T07:15:00Z] [INFO]  api-gateway healthy — no errors detected\n"
                "[2026-04-05T07:14:30Z] [INFO]  latency p99: 450ms (elevated due to upstream worker backpressure)\n"
                "[2026-04-05T07:14:00Z] [INFO]  not the source of this issue — problem is in worker-node capacity"
            ),
        },
        "deployment_version": "v1.4.0",
    },
    "medium": {
        "id": "medium",
        "name": "The Poison Pill",
        "difficulty": "medium",
        "description": (
            "API error rate spiked to 15% immediately after deployment v2.1.0. "
            "Diagnose the root cause and take corrective action."
        ),
        "max_attempts": 10,
        "alerts": [
            {
                "severity": "critical",
                "service": "api-gateway",
                "message": "API error rate spike: 15% of requests returning 500",
            },
            {
                "severity": "info",
                "service": "api-gateway",
                "message": "Deployment completed: v2.1.0 rolled out to all pods",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "degraded",
                "replicas": 4,
                "cpu": 55.0,
                "version": "v2.1.0",
                "error_rate": 15.0,
            },
            "worker-node": {"status": "healthy", "replicas": 3, "cpu": 30.0},
            "database": {"status": "healthy", "connections": 60},
            "cache-layer": {"status": "healthy", "hit_rate": 85.0},
        },
        "metrics": {
            "cpu_percent": 55.0,
            "memory_percent": 52.0,
            "queue_depth": 20,
            "error_rate_percent": 15.0,
            "latency_p99_ms": 1200,
            "db_connections": 60,
        },
        "logs": {
            "api-gateway": (
                "[2026-04-05T08:00:15Z] [CRITICAL] java.lang.NullPointerException: PaymentHandler.processOrder(PaymentHandler.java:142)\n"
                "[2026-04-05T08:00:15Z] [CRITICAL]   at com.app.payment.PaymentHandler.validateCard(PaymentHandler.java:89)\n"
                "[2026-04-05T08:00:15Z] [CRITICAL]   at com.app.api.CheckoutController.handlePost(CheckoutController.java:55)\n"
                "[2026-04-05T08:00:10Z] [ERROR] req_id=p-3391 trace_id=tx-7702 HTTP 500: NullPointerException in payment validation path\n"
                "[2026-04-05T08:00:05Z] [ERROR] 15% of requests hitting null reference — all on /checkout endpoint\n"
                "[2026-04-05T07:59:50Z] [WARN]  error rate climbing: 15.0% and rising — customer impact confirmed\n"
                "[2026-04-05T07:59:30Z] [WARN]  errors correlate exactly with v2.1.0 rollout (deployed 45 min ago)\n"
                "[2026-04-05T07:59:00Z] [INFO]  v2.1.0 changelog: refactored PaymentHandler to support new card types\n"
                "[2026-04-05T07:58:30Z] [INFO]  rollback candidate: v2.0.9 (last stable, ran for 14 days with 0.1% error rate)\n"
                "[2026-04-05T07:58:00Z] [INFO]  v2.0.8 also stable but older — prefer v2.0.9\n"
                "[2026-04-05T07:15:00Z] [INFO]  deployment v2.1.0 rolled out to all 4 pods"
            ),
            "worker-node": (
                "[2026-04-05T08:00:00Z] [INFO]  worker-node processing normally — no errors in pipeline\n"
                "[2026-04-05T07:59:30Z] [INFO]  message throughput: 150 msg/min — within normal range\n"
                "[2026-04-05T07:59:00Z] [INFO]  CPU 30%, memory 45% — healthy\n"
                "[2026-04-05T07:58:00Z] [INFO]  not affected by api-gateway issue — different code path"
            ),
            "database": (
                "[2026-04-05T08:00:00Z] [INFO]  connections: 60/200 — stable and healthy\n"
                "[2026-04-05T07:59:30Z] [INFO]  query latency p99: 8ms — normal\n"
                "[2026-04-05T07:59:00Z] [INFO]  no slow queries, no locks detected\n"
                "[2026-04-05T07:58:00Z] [INFO]  database is NOT the source of this issue"
            ),
            "cache-layer": (
                "[2026-04-05T08:00:00Z] [INFO]  cache hit rate 85% — nominal\n"
                "[2026-04-05T07:59:00Z] [INFO]  no cache-related errors — operating normally"
            ),
        },
        "deployment_version": "v2.1.0",
    },
    "memory_leak": {
        "id": "memory_leak",
        "name": "The Silent OOM",
        "difficulty": "medium-hard",
        "description": (
            "Payment-service pods keep OOM-killing every ~30 minutes. "
            "Restarts temporarily fix it, but the leak returns. "
            "Identify the leaking component, mitigate the immediate impact, "
            "and apply the permanent fix."
        ),
        "max_attempts": 12,
        "alerts": [
            {
                "severity": "critical",
                "service": "payment-service",
                "message": "OOMKilled: pod payment-service-7b9f4 restarted 6 times in 3 hours",
            },
            {
                "severity": "warning",
                "service": "payment-service",
                "message": "Memory usage: 1.8Gi / 2Gi limit — 90% utilised",
            },
            {
                "severity": "info",
                "service": "api-gateway",
                "message": "Intermittent 502s on /checkout endpoint — upstream payment-service unreachable during restarts",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "degraded",
                "replicas": 3,
                "cpu": 35.0,
                "version": "v4.1.0",
                "error_rate": 8.0,
            },
            "payment-service": {
                "status": "critical",
                "replicas": 3,
                "healthy_replicas": 1,
                "cpu": 40.0,
                "memory_percent": 90.0,
                "version": "v4.1.0",
                "restarts": 6,
            },
            "cache-layer": {
                "status": "healthy",
                "hit_rate": 92.0,
                "memory_percent": 75.0,
            },
            "database": {"status": "healthy", "connections": 55, "max_connections": 200},
            "worker-node": {"status": "healthy", "replicas": 3, "cpu": 25.0},
        },
        "metrics": {
            "cpu_percent": 40.0,
            "memory_percent": 90.0,
            "queue_depth": 45,
            "error_rate_percent": 8.0,
            "latency_p99_ms": 900,
            "db_connections": 55,
        },
        "logs": {
            "payment-service": (
                "[2026-04-05T09:12:03Z] [ERROR] container=payment-service-7b9f4 reason=OOMKilled exitCode=137\n"
                "[2026-04-05T09:12:03Z] [ERROR] pod restarted — 6th restart in 3 hours (CrashLoopBackOff imminent)\n"
                "[2026-04-05T09:11:58Z] [WARN]  memory usage 1.83Gi / 2Gi (91.5%) — approaching limit\n"
                "[2026-04-05T09:10:42Z] [WARN]  GC overhead: 45% of CPU time spent in garbage collection\n"
                "[2026-04-05T08:55:17Z] [DEBUG] /internal/product-catalog-cache size=482,291 objects, 1.2Gi heap\n"
                "[2026-04-05T08:55:17Z] [DEBUG] cache eviction policy: NONE — entries never expire\n"
                "[2026-04-05T08:41:00Z] [INFO]  heap dump analysis: 68% of heap held by ProductCatalogCache\n"
                "[2026-04-05T08:40:55Z] [INFO]  ProductCatalogCache grows ~50MB every 10 minutes (no TTL configured)\n"
                "[2026-04-05T08:30:12Z] [INFO]  v4.1.0 deployed 5 hours ago — introduced /internal/product-catalog-cache endpoint\n"
                "[2026-04-05T08:30:12Z] [INFO]  feature flag: PRODUCT_CACHE_ENABLED=true (new in v4.1.0)\n"
                "[2026-04-05T08:15:00Z] [INFO]  payment processing nominal on surviving pod\n"
                "[2026-04-05T04:12:00Z] [INFO]  deployment v4.1.0 rolled out — changelog: added product catalog cache for faster checkout"
            ),
            "api-gateway": (
                "[2026-04-05T09:12:10Z] [ERROR] 502 Bad Gateway — upstream payment-service-7b9f4 connection refused\n"
                "[2026-04-05T09:12:05Z] [WARN]  /checkout latency spike: p99=900ms (normal: 150ms)\n"
                "[2026-04-05T09:11:00Z] [INFO]  circuit breaker half-open on payment-service — 2/3 pods unhealthy\n"
                "[2026-04-05T08:42:00Z] [INFO]  8% of requests to /checkout returning 502\n"
                "[2026-04-05T08:30:00Z] [INFO]  no recent deploys to api-gateway — last deploy v4.0.2, 2 weeks ago"
            ),
            "cache-layer": (
                "[2026-04-05T09:10:00Z] [INFO]  Redis cache hit rate 92% — operating normally\n"
                "[2026-04-05T09:10:00Z] [INFO]  memory usage 3.0Gi / 4Gi — within limits\n"
                "[2026-04-05T08:00:00Z] [INFO]  no eviction pressure, all keys within TTL"
            ),
            "database": (
                "[2026-04-05T09:10:00Z] [INFO]  connections: 55/200 — healthy\n"
                "[2026-04-05T09:10:00Z] [INFO]  query latency p99: 12ms — normal\n"
                "[2026-04-05T08:00:00Z] [INFO]  no slow queries detected"
            ),
        },
        "deployment_version": "v4.1.0",
    },
    "cert_expiry": {
        "id": "cert_expiry",
        "name": "The Midnight Expiry",
        "difficulty": "expert",
        "description": (
            "All inter-service communication failing with TLS handshake errors. "
            "A recent deployment looks suspicious and CPU is elevated, but the "
            "real cause is an expired mTLS certificate in the service mesh. "
            "Navigate red herrings, trace the root cause, rotate the cert, "
            "and restart all affected services."
        ),
        "max_attempts": 20,
        "alerts": [
            {
                "severity": "critical",
                "service": "api-gateway",
                "message": "95% of inter-service requests failing with TLS handshake error",
            },
            {
                "severity": "critical",
                "service": "worker-node",
                "message": "All outbound requests to payment-service and database failing",
            },
            {
                "severity": "warning",
                "service": "payment-service",
                "message": "Inbound connections rejected: TLS certificate validation failed",
            },
            {
                "severity": "info",
                "service": "api-gateway",
                "message": "Deployment v5.0.0 completed 2 hours ago (routine dependency bump)",
            },
            {
                "severity": "warning",
                "service": "load-balancer",
                "message": "CPU spike to 88% — increased TLS retry storms",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "critical",
                "replicas": 4,
                "cpu": 88.0,
                "version": "v5.0.0",
                "error_rate": 95.0,
                "tls_errors": 4820,
            },
            "payment-service": {
                "status": "critical",
                "replicas": 3,
                "cpu": 72.0,
                "version": "v4.1.0",
                "error_rate": 95.0,
                "tls_errors": 3100,
            },
            "worker-node": {
                "status": "critical",
                "replicas": 4,
                "cpu": 65.0,
                "version": "v3.2.1",
                "error_rate": 90.0,
            },
            "database": {
                "status": "degraded",
                "connections": 12,
                "max_connections": 200,
                "ssl_status": "handshake_failing",
            },
            "service-mesh-proxy": {
                "status": "critical",
                "type": "envoy-sidecar",
                "cert_expiry": "2026-04-05T00:00:00Z",
                "cert_status": "EXPIRED",
                "last_rotation": "2025-04-05T00:00:00Z",
            },
            "load-balancer": {
                "status": "degraded",
                "cpu": 88.0,
                "active_connections": 50,
                "tls_retry_rate": "1200/min",
            },
            "cache-layer": {"status": "healthy", "hit_rate": 10.0, "note": "low hit rate due to no inbound traffic"},
        },
        "metrics": {
            "cpu_percent": 88.0,
            "memory_percent": 60.0,
            "queue_depth": 2500,
            "error_rate_percent": 95.0,
            "latency_p99_ms": 30000,
            "db_connections": 12,
        },
        "logs": {
            "api-gateway": (
                "[2026-04-05T00:01:15Z] [CRITICAL] req_id=a3f8c TLS handshake failed: certificate has expired\n"
                "[2026-04-05T00:01:15Z] [CRITICAL] x509: certificate signed by unknown authority (expired root)\n"
                "[2026-04-05T00:01:14Z] [ERROR] upstream payment-service: TLS error — peer certificate not valid after 2026-04-05T00:00:00Z\n"
                "[2026-04-05T00:01:10Z] [ERROR] envoy sidecar: mTLS handshake rejected — client cert expired\n"
                "[2026-04-05T00:01:05Z] [WARN]  95% of outbound requests failing — circuit breaker OPEN\n"
                "[2026-04-05T00:00:45Z] [WARN]  CPU spike to 88% — TLS retry storms consuming resources\n"
                "[2026-04-05T00:00:30Z] [INFO]  deployment v5.0.0 completed 2 hours ago — routine dependency version bump\n"
                "[2026-04-05T00:00:30Z] [INFO]  v5.0.0 changelog: bumped lodash 4.17.20->4.17.21, no service mesh changes\n"
                "[2026-04-04T22:00:00Z] [INFO]  pre-deploy health check: all TLS certs valid, mesh healthy\n"
                "[2026-04-04T21:58:00Z] [INFO]  NOTE: service mesh certs last rotated 2025-04-05 (365-day validity)"
            ),
            "payment-service": (
                "[2026-04-05T00:01:20Z] [CRITICAL] javax.net.ssl.SSLHandshakeException: PKIX path validation failed\n"
                "[2026-04-05T00:01:20Z] [CRITICAL] Caused by: java.security.cert.CertificateExpiredException: NotAfter: Sat Apr 05 00:00:00 UTC 2026\n"
                "[2026-04-05T00:01:18Z] [ERROR] inbound mTLS: client certificate expired — rejecting connection from api-gateway\n"
                "[2026-04-05T00:01:15Z] [ERROR] inbound mTLS: client certificate expired — rejecting connection from worker-node\n"
                "[2026-04-05T00:01:10Z] [WARN]  all inbound connections failing TLS validation\n"
                "[2026-04-05T00:00:50Z] [INFO]  service code healthy — no application errors in payment logic\n"
                "[2026-04-05T00:00:50Z] [INFO]  last code deploy: v4.1.0 (5 hours ago) — no TLS changes\n"
                "[2026-04-05T00:00:30Z] [INFO]  check service-mesh-proxy for cert status"
            ),
            "worker-node": (
                "[2026-04-05T00:01:25Z] [ERROR] gRPC call to payment-service failed: UNAVAILABLE: TLS handshake error\n"
                "[2026-04-05T00:01:22Z] [ERROR] gRPC call to database failed: UNAVAILABLE: TLS handshake error\n"
                "[2026-04-05T00:01:20Z] [ERROR] all downstream calls failing — request queue growing (2500 pending)\n"
                "[2026-04-05T00:01:15Z] [WARN]  retry budget exhausted — dropping requests\n"
                "[2026-04-05T00:00:30Z] [INFO]  no recent deploys to worker-node — last deploy v3.2.1 (1 week ago)\n"
                "[2026-04-05T00:00:30Z] [INFO]  application code healthy — issue is in transport layer"
            ),
            "database": (
                "[2026-04-05T00:01:30Z] [ERROR] SSL connection rejected: client certificate expired\n"
                "[2026-04-05T00:01:28Z] [ERROR] only 12 connections active (normally 120+) — SSL clients can't connect\n"
                "[2026-04-05T00:01:25Z] [WARN]  pg_hba.conf requires SSL for all connections — no fallback to plaintext\n"
                "[2026-04-05T00:00:30Z] [INFO]  database engine healthy — issue is certificate-based, not data-layer\n"
                "[2026-04-05T00:00:30Z] [INFO]  cert used for client auth issued by service-mesh CA — check mesh proxy"
            ),
            "service-mesh-proxy": (
                "[2026-04-05T00:00:01Z] [CRITICAL] ROOT CAUSE: mTLS certificate expired at 2026-04-05T00:00:00Z\n"
                "[2026-04-05T00:00:01Z] [CRITICAL] cert subject=*.internal.mesh, issuer=mesh-ca, notAfter=2026-04-05T00:00:00Z\n"
                "[2026-04-05T00:00:01Z] [ERROR] envoy proxy: all mTLS handshakes failing — cert rotation required\n"
                "[2026-04-05T00:00:00Z] [ERROR] certificate validity check: EXPIRED (was valid for 365 days, issued 2025-04-05)\n"
                "[2026-04-04T23:55:00Z] [WARN]  cert expiry in 5 minutes — ALERT WAS SENT but not acknowledged\n"
                "[2026-04-04T23:00:00Z] [WARN]  cert expiry in 1 hour — automated rotation failed: permission denied on vault\n"
                "[2026-04-04T22:00:00Z] [INFO]  scheduled cert rotation attempted — vault token expired, rotation aborted\n"
                "[2026-04-04T22:00:00Z] [INFO]  ACTION REQUIRED: manual cert rotation via rotate_certs command"
            ),
            "load-balancer": (
                "[2026-04-05T00:01:30Z] [WARN]  CPU 88% — TLS retry storms from downstream services\n"
                "[2026-04-05T00:01:20Z] [WARN]  1200 TLS retries/min — backends rejecting handshakes\n"
                "[2026-04-05T00:01:00Z] [INFO]  load-balancer config unchanged — issue is backend TLS, not LB\n"
                "[2026-04-05T00:00:30Z] [INFO]  external TLS (client-facing) is fine — issue is internal mTLS only"
            ),
        },
        "deployment_version": "v5.0.0",
    },
    "hard": {
        "id": "hard",
        "name": "The Cascading Lock",
        "difficulty": "hard",
        "description": (
            "Multiple services are failing. API gateway returning 504s, "
            "workers in CrashLoopBackOff, database connection pool nearly "
            "exhausted. A recent config change and memory spike add confusion. "
            "Find the true root cause and resolve the cascading failure."
        ),
        "max_attempts": 15,
        "alerts": [
            {
                "severity": "critical",
                "service": "api-gateway",
                "message": "API gateway timeout: 40% of requests returning 504",
            },
            {
                "severity": "critical",
                "service": "worker-node",
                "message": (
                    "Worker pods unresponsive: 3/4 in CrashLoopBackOff"
                ),
            },
            {
                "severity": "warning",
                "service": "database",
                "message": "Connection pool near exhaustion: 195/200 connections in use",
            },
            {
                "severity": "info",
                "service": "worker-node",
                "message": "Config change deployed 30 min ago: increased worker thread pool from 50 to 100",
            },
            {
                "severity": "warning",
                "service": "cache-layer",
                "message": "Memory usage spiked to 85% — possible leak",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "critical",
                "replicas": 4,
                "cpu": 70.0,
                "version": "v3.2.1",
                "error_rate": 40.0,
            },
            "worker-node": {
                "status": "critical",
                "replicas": 4,
                "healthy_replicas": 1,
                "cpu": 98.0,
                "version": "v3.2.1",
                "last_config_change": "thread_pool: 50->100 (30 min ago)",
            },
            "database": {
                "status": "degraded",
                "connections": 195,
                "max_connections": 200,
                "locked_queries": [
                    {
                        "pid": "4287",
                        "state": "LOCKED",
                        "query": "UPDATE orders SET status='processing' WHERE ...",
                        "duration": "45m",
                        "blocking": True,
                    },
                    {
                        "pid": "4290",
                        "state": "WAITING",
                        "query": "SELECT * FROM orders WHERE ...",
                        "duration": "30m",
                        "blocking": False,
                    },
                    {
                        "pid": "4295",
                        "state": "WAITING",
                        "query": "INSERT INTO audit_log ...",
                        "duration": "28m",
                        "blocking": False,
                    },
                ],
            },
            "cache-layer": {
                "status": "degraded",
                "hit_rate": 12.0,
                "memory_percent": 85.0,
            },
        },
        "metrics": {
            "cpu_percent": 98.0,
            "memory_percent": 85.0,
            "queue_depth": 800,
            "error_rate_percent": 40.0,
            "latency_p99_ms": 8500,
            "db_connections": 195,
        },
        "logs": {
            "api-gateway": (
                "[2026-04-05T08:30:15Z] [CRITICAL] req_id=e7a21 trace_id=abc-001 504 Gateway Timeout — upstream worker-node:8080 not responding after 30s\n"
                "[2026-04-05T08:30:10Z] [ERROR] req_id=e7a20 trace_id=abc-002 504 Gateway Timeout — upstream worker-node:8080 connection refused\n"
                "[2026-04-05T08:29:55Z] [ERROR] 40% of requests failing with timeout (30s) — error budget exhausted\n"
                "[2026-04-05T08:29:30Z] [WARN]  connection pool to worker-node saturated: 100/100 active connections\n"
                "[2026-04-05T08:29:00Z] [WARN]  circuit breaker OPEN for worker-node — 3 consecutive failures\n"
                "[2026-04-05T08:28:00Z] [INFO]  api-gateway v3.2.1 — no recent code changes\n"
                "[2026-04-05T08:28:00Z] [INFO]  investigate worker-node health — timeouts originate downstream"
            ),
            "worker-node": (
                "[2026-04-05T08:30:20Z] [CRITICAL] pod worker-node-3 OOMKilled (exit 137): memory 1.9Gi/2Gi at time of kill\n"
                "[2026-04-05T08:30:18Z] [CRITICAL] pod worker-node-2 OOMKilled — CrashLoopBackOff (restart count: 8)\n"
                "[2026-04-05T08:30:15Z] [CRITICAL] pod worker-node-4 OOMKilled — CrashLoopBackOff (restart count: 5)\n"
                "[2026-04-05T08:29:50Z] [ERROR] surviving pod worker-node-1: all DB queries hanging >30s\n"
                "[2026-04-05T08:29:45Z] [ERROR] java.sql.SQLTimeoutException: query timed out after 30000ms\n"
                "[2026-04-05T08:29:40Z] [WARN]  thread pool exhaustion: 100/100 threads blocked on DB I/O\n"
                "[2026-04-05T08:29:00Z] [INFO]  config change 30 min ago: thread pool 50->100 — this increased DB connection demand\n"
                "[2026-04-05T08:29:00Z] [INFO]  NOTE: thread pool increase is NOT the root cause — queries are hanging because of a DB lock, not capacity\n"
                "[2026-04-05T08:28:30Z] [INFO]  OOM is a side-effect: blocked threads accumulate memory while waiting\n"
                "[2026-04-05T08:28:00Z] [INFO]  root cause is in database layer — check database logs for locks"
            ),
            "database": (
                "[2026-04-05T08:30:25Z] [CRITICAL] LOCK ESCALATION: PID 4287 holding ROW EXCLUSIVE lock on 'orders' table for 45 minutes\n"
                "[2026-04-05T08:30:20Z] [CRITICAL] lock_monitor: 47 queries blocked by PID 4287 — deadlock risk HIGH\n"
                "[2026-04-05T08:30:15Z] [ERROR] connection pool at 195/200 — 5 connections remaining\n"
                "[2026-04-05T08:30:10Z] [ERROR] new connections timing out in handshake — pool near exhaustion\n"
                "[2026-04-05T08:29:30Z] [WARN]  PID 4287: UPDATE orders SET status='processing' WHERE batch_id='BID-90210'\n"
                "[2026-04-05T08:29:30Z] [WARN]  PID 4287 acquired lock at 07:45:00Z — 45 min ago, no progress\n"
                "[2026-04-05T08:29:00Z] [WARN]  PID 4290 (SELECT * FROM orders): WAITING on PID 4287 for 30 min\n"
                "[2026-04-05T08:29:00Z] [WARN]  PID 4295 (INSERT INTO audit_log): WAITING on PID 4287 for 28 min\n"
                "[2026-04-05T08:28:30Z] [INFO]  pg_stat_activity shows 47 queries in 'Lock wait' state\n"
                "[2026-04-05T08:28:00Z] [INFO]  ACTION REQUIRED: kill PID 4287 to release exclusive lock\n"
                "[2026-04-05T08:28:00Z] [INFO]  CAUTION: PID 4290 and 4295 are WAITING (victims, not blockers) — do not kill these"
            ),
            "cache-layer": (
                "[2026-04-05T08:30:00Z] [WARN]  memory 85% — elevated but within safe operating range\n"
                "[2026-04-05T08:29:30Z] [INFO]  hit rate dropped to 12% — consequence of reduced traffic, not a cache issue\n"
                "[2026-04-05T08:29:00Z] [INFO]  cache invalidation and TTL operating normally\n"
                "[2026-04-05T08:28:00Z] [INFO]  memory spike correlates with increased connection retry buffers — will normalise once upstream recovers"
            ),
        },
        "deployment_version": "v3.2.1",
    },
}


# ---------------------------------------------------------------------------
# Internal mutable task state (not Pydantic — plain class)
# ---------------------------------------------------------------------------


class _TaskState:
    """Per-episode mutable state that tracks the simulation."""

    def __init__(self, task_id: str) -> None:
        cfg = TASK_CONFIGS[task_id]
        self.task_id = task_id
        self.difficulty = cfg["difficulty"]
        self.alerts: List[Dict[str, Any]] = copy.deepcopy(cfg["alerts"])
        self.services: Dict[str, Any] = copy.deepcopy(cfg["services"])
        self.metrics: Dict[str, Any] = copy.deepcopy(cfg["metrics"])
        self.logs: Dict[str, str] = copy.deepcopy(cfg["logs"])
        self.deployment_version: str = cfg["deployment_version"]
        self.max_attempts: int = cfg["max_attempts"]

        self.step_count: int = 0
        self.cumulative_reward: float = 0.0
        self.cloud_cost: float = 0.0
        self.downtime_minutes: float = 0.0
        self.uptime: float = 100.0
        self.actions_taken: List[str] = []
        self.done: bool = False

        # Task-specific flags ------------------------------------------------
        # Task 1
        self.queue_length: int = cfg["metrics"].get("queue_depth", 0)
        self.worker_replicas: int = (
            cfg["services"].get("worker-node", {}).get("replicas", 2)
        )

        # Task 2
        self.has_queried_logs: bool = False
        self.has_rolled_back: bool = False
        self.scaled_broken_service: bool = False

        # Task 3
        self.queried_api_gateway_logs: bool = False
        self.queried_worker_logs: bool = False
        self.queried_db_logs: bool = False
        self.queried_cache_logs: bool = False
        self.identified_pid: bool = False
        self.killed_query: bool = False
        self.stabilized: bool = False

        # Task 4 — Memory Leak
        self.queried_payment_logs: bool = False
        self.queried_api_gw_logs_ml: bool = False
        self.identified_leak: bool = False
        self.restarted_payment: bool = False
        self.rolled_back_payment: bool = False

        # Task 5 — Certificate Expiry
        self.queried_api_gw_logs_ce: bool = False
        self.queried_payment_logs_ce: bool = False
        self.queried_worker_logs_ce: bool = False
        self.queried_db_logs_ce: bool = False
        self.queried_mesh_logs: bool = False
        self.queried_lb_logs: bool = False
        self.identified_cert_issue: bool = False
        self.rotated_certs: bool = False
        self.rolled_back_deploy_ce: bool = False
        self.restarted_services: set = set()  # track which services restarted


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

_MAX_REWARDS = {
    "easy": 0.4,
    "medium": 1.0,
    "hard": 1.0,
    "medium-hard": 0.9,
    "expert": 0.95,
}


def _normalised_score(difficulty: str, cumulative: float) -> float:
    mx = _MAX_REWARDS.get(difficulty, 1.0)
    return max(0.0, min(cumulative / mx, 1.0))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class SREIncidentEnvironment(Environment[SREAction, SREObservation, SREState]):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ts: Optional[_TaskState] = None
        self._episode_id: Optional[str] = None

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SREObservation:
        task_id = kwargs.get("task_id", "easy")
        if task_id not in TASK_CONFIGS:
            task_id = "easy"

        self._episode_id = episode_id or str(uuid.uuid4())
        self._ts = _TaskState(task_id)

        return self._build_observation(
            reward=None,
            feedback=f"Incident opened: {TASK_CONFIGS[task_id]['name']}. "
            f"{TASK_CONFIGS[task_id]['description']}",
            hint="Review the active alerts and system metrics, then decide on your first action.",
        )

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------

    def step(
        self,
        action: SREAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> SREObservation:
        ts = self._ts
        if ts is None:
            return SREObservation(
                done=True,
                reward=0.0,
                feedback="Environment not initialised. Call reset() first.",
            )
        if ts.done:
            return self._build_observation(
                reward=0.0,
                feedback="Incident already closed. Call reset() for a new episode.",
            )

        ts.step_count += 1
        ts.cloud_cost += 0.50
        ts.downtime_minutes += 1.0
        ts.actions_taken.append(action.action_type)

        # Dispatch to the appropriate task handler
        handler = {
            "easy": self._step_easy,
            "medium": self._step_medium,
            "hard": self._step_hard,
            "memory_leak": self._step_memory_leak,
            "cert_expiry": self._step_cert_expiry,
        }.get(ts.task_id, self._step_easy)

        reward, feedback, hint = handler(action)

        ts.cumulative_reward += reward

        # Check max attempts
        if not ts.done and ts.step_count >= ts.max_attempts:
            ts.done = True
            feedback += " Max steps reached — incident auto-closed."

        return self._build_observation(reward=reward, feedback=feedback, hint=hint)

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @property
    def state(self) -> SREState:
        ts = self._ts
        if ts is None:
            return SREState(episode_id=self._episode_id)
        return SREState(
            episode_id=self._episode_id,
            step_count=ts.step_count,
            task_id=ts.task_id,
            difficulty=ts.difficulty,
            current_score=_normalised_score(ts.difficulty, ts.cumulative_reward),
            total_downtime_minutes=ts.downtime_minutes,
            total_cost_usd=ts.cloud_cost,
            actions_taken=list(ts.actions_taken),
            completed=ts.done,
        )

    # ==================================================================
    # Task 1 — The Traffic Spike
    # ==================================================================

    def _step_easy(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # --- Queue dynamics (applied before action processing) ---
        growth = 200
        drain = ts.worker_replicas * 100
        ts.queue_length = max(0, ts.queue_length + growth - drain)

        at = action.action_type

        if at == "scale_service":
            if action.service_name != "worker-node":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' is not the bottleneck. "
                    "The worker-node is the service that needs scaling."
                )
            elif action.replicas <= ts.worker_replicas:
                reward = -0.1
                feedback = (
                    f"Replicas must be increased (currently {ts.worker_replicas}). "
                    "Scaling down during an incident is counter-productive."
                )
            else:
                old = ts.worker_replicas
                ts.worker_replicas = action.replicas
                ts.services["worker-node"]["replicas"] = action.replicas
                ts.services["worker-node"]["cpu"] = max(
                    30.0, 92.0 * (2 / max(action.replicas, 1))
                )
                reward = 0.2
                feedback = (
                    f"Scaled worker-node from {old} to {action.replicas} replicas. "
                    f"Drain rate now {action.replicas * 100} msg/min."
                )

        elif at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                feedback = f"Logs for {svc}:\n{ts.logs[svc]}"
            else:
                feedback = f"No logs available for '{svc}'. Valid services: {', '.join(ts.logs.keys())}"

        elif at == "resolve_incident":
            if ts.queue_length >= 50:
                reward = -0.2
                feedback = (
                    f"Cannot resolve — queue still has {ts.queue_length} messages. "
                    "Drain the backlog first."
                )
            else:
                ts.done = True
                feedback = "Incident resolved! Queue fully drained."

        elif at == "rollback_deployment":
            reward = -0.1
            feedback = "No bad deployment detected. This is a scaling issue, not a code issue."

        elif at == "kill_query":
            reward = -0.1
            feedback = "No database lock detected. Focus on scaling the workers."

        elif at == "restart_service":
            reward = -0.1
            feedback = "Restarting won't help. The queue is growing because there aren't enough workers."

        elif at == "rotate_certs":
            reward = -0.1
            feedback = "No certificate issues detected. This is a scaling problem."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Update metrics
        ts.metrics["queue_depth"] = ts.queue_length
        ts.services["order-processing-queue"]["queue_length"] = ts.queue_length

        # Queue overflow penalty
        if ts.queue_length >= 1000:
            reward -= 0.1
            ts.queue_length = 1000
            ts.metrics["queue_depth"] = 1000
            feedback += " CRITICAL: Queue overflow — messages being dropped!"
            if not any(
                a.get("message", "").startswith("Queue overflow")
                for a in ts.alerts
            ):
                ts.alerts.append(
                    {
                        "severity": "critical",
                        "service": "order-processing-queue",
                        "message": "Queue overflow! Messages dropped.",
                    }
                )
        elif ts.queue_length > 800:
            reward -= 0.1
            feedback += f" WARNING: Queue at {ts.queue_length}/1000 — nearing overflow."

        # Auto-resolve check
        if ts.queue_length < 50 and not ts.done:
            reward += 0.2
            ts.done = True
            feedback += " Queue drained successfully — incident auto-resolved!"

        # Hints
        if ts.step_count >= 3 and ts.queue_length >= 500:
            hint = (
                "Hint: The queue is growing because the 2 workers can only "
                "drain 200 msg/min but 200 msg/min are arriving. Scale "
                "worker-node to 5+ replicas."
            )

        ts.uptime = max(90.0, ts.uptime - 0.5)
        return reward, feedback, hint

    # ==================================================================
    # Task 2 — The Poison Pill
    # ==================================================================

    def _step_medium(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation while bug is live
        if not ts.has_rolled_back:
            ts.uptime = max(80.0, ts.uptime - 0.3)
            ts.metrics["latency_p99_ms"] = min(
                5000, ts.metrics["latency_p99_ms"] + 200
            )

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                if svc == "api-gateway" and not ts.has_queried_logs:
                    ts.has_queried_logs = True
                    reward = 0.4
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "Root cause identified: NullPointerException in v2.1.0 "
                        "PaymentHandler."
                    )
                else:
                    feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed)"
            else:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )

        elif at == "rollback_deployment":
            if action.service_name != "api-gateway":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' doesn't need a rollback. "
                    "The api-gateway running v2.1.0 is the problem."
                )
            elif action.version != "v2.0.9":
                reward = -0.1
                feedback = (
                    f"Version '{action.version}' is not correct. "
                    "The last stable version is v2.0.9."
                )
            elif ts.has_rolled_back:
                feedback = "Already rolled back. No further action needed."
            else:
                ts.has_rolled_back = True
                ts.deployment_version = "v2.0.9"
                ts.services["api-gateway"]["version"] = "v2.0.9"
                ts.services["api-gateway"]["status"] = "healthy"
                ts.services["api-gateway"]["error_rate"] = 0.5
                ts.metrics["error_rate_percent"] = 0.5
                ts.metrics["latency_p99_ms"] = 150
                ts.alerts = [
                    a
                    for a in ts.alerts
                    if "error rate" not in a.get("message", "").lower()
                ]
                reward = 0.6
                feedback = (
                    "Rolled back api-gateway from v2.1.0 to v2.0.9. "
                    "Error rate dropped to 0.5%. Incident resolved!"
                )
                ts.done = True

        elif at == "scale_service":
            if action.service_name == "api-gateway":
                ts.scaled_broken_service = True
                reward = -0.5
                feedback = (
                    "CRITICAL MISTAKE: Scaling a service with a code bug just "
                    "multiplies the errors! The issue is in v2.1.0's code, "
                    "not capacity. Consider rolling back instead."
                )
            else:
                reward = -0.1
                feedback = (
                    f"Scaling '{action.service_name}' won't help. "
                    "The error rate is caused by a code bug, not load."
                )

        elif at == "resolve_incident":
            if not ts.has_rolled_back:
                reward = -0.2
                feedback = (
                    "Cannot resolve — error rate is still at "
                    f"{ts.metrics['error_rate_percent']}%. "
                    "The root cause (v2.1.0 bug) has not been addressed."
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        elif at == "kill_query":
            reward = -0.1
            feedback = (
                "No database issue detected. This incident is caused by a "
                "bad deployment, not a DB lock."
            )

        elif at == "restart_service":
            reward = -0.1
            feedback = (
                "Restarting won't fix a code bug — the bad code will just reload. "
                "Roll back to the last stable version instead."
            )

        elif at == "rotate_certs":
            reward = -0.1
            feedback = "No certificate issues detected. This is a bad deployment issue."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints
        if ts.step_count >= 2 and not ts.has_queried_logs:
            hint = (
                "Hint: Check the api-gateway logs to understand why the "
                "error rate is 15%."
            )
        elif ts.step_count >= 4 and ts.has_queried_logs and not ts.has_rolled_back:
            hint = (
                "Hint: The logs showed a NullPointerException in v2.1.0. "
                "Roll back api-gateway to v2.0.9."
            )

        return reward, feedback, hint

    # ==================================================================
    # Task 3 — The Cascading Lock
    # ==================================================================

    def _step_hard(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation until lock is killed
        if not ts.killed_query:
            ts.metrics["error_rate_percent"] = min(
                80.0, ts.metrics["error_rate_percent"] + 5.0
            )
            ts.metrics["latency_p99_ms"] = min(
                30000, ts.metrics["latency_p99_ms"] + 2000
            )
            ts.metrics["db_connections"] = min(
                200, ts.metrics["db_connections"] + 2
            )
            ts.uptime = max(60.0, ts.uptime - 1.0)

            if ts.metrics["db_connections"] >= 200:
                if not any(
                    "full block" in a.get("message", "").lower()
                    for a in ts.alerts
                ):
                    ts.alerts.append(
                        {
                            "severity": "critical",
                            "service": "database",
                            "message": (
                                "FULL BLOCK: Connection pool exhausted "
                                "(200/200). All new connections rejected."
                            ),
                        }
                    )

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                if svc == "api-gateway" and not ts.queried_api_gateway_logs:
                    ts.queried_api_gateway_logs = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "The api-gateway is timing out on worker-node requests. "
                        "Investigate worker-node next."
                    )
                elif svc == "worker-node" and not ts.queried_worker_logs:
                    ts.queried_worker_logs = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "Workers are timing out on database queries. "
                        "The config change (thread pool 50→100) increased DB demand "
                        "but is NOT the root cause — queries are hanging due to a DB lock."
                    )
                elif svc == "database" and not ts.queried_db_logs:
                    ts.queried_db_logs = True
                    ts.identified_pid = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "ROOT CAUSE FOUND: PID 4287 is holding an exclusive "
                        "lock for 45 minutes, blocking 47 other queries. "
                        "Kill this query to release the lock. "
                        "NOTE: PID 4290 and 4295 are victims (WAITING), not blockers."
                    )
                elif svc == "cache-layer" and not ts.queried_cache_logs:
                    ts.queried_cache_logs = True
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "Cache memory spike is a side-effect of retry buffers, "
                        "not the root cause. It will normalise once the upstream issue is fixed."
                    )
                else:
                    feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed)"
            else:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )

        elif at == "kill_query":
            if ts.killed_query:
                feedback = "Lock already killed. Focus on stabilising the system."
            elif action.query_id == "4287":
                ts.killed_query = True
                reward = 0.4
                # Update system state post-kill
                ts.metrics["db_connections"] = 60
                ts.metrics["error_rate_percent"] = 15.0
                ts.metrics["latency_p99_ms"] = 3000
                ts.services["database"]["connections"] = 60
                ts.services["database"]["locked_queries"] = []
                ts.services["database"]["status"] = "recovering"
                ts.services["worker-node"]["status"] = "recovering"
                ts.services["worker-node"]["healthy_replicas"] = 1
                ts.queue_length = 600
                ts.metrics["queue_depth"] = 600

                # Update alerts
                ts.alerts = [
                    a
                    for a in ts.alerts
                    if "connection pool" not in a.get("message", "").lower()
                ]
                ts.alerts.append(
                    {
                        "severity": "warning",
                        "service": "worker-node",
                        "message": (
                            "Workers recovering but backlog at 600 messages. "
                            "Scale worker-node to >=4 replicas to drain backlog."
                        ),
                    }
                )
                feedback = (
                    "Killed PID 4287 — database lock released! "
                    "Connections dropped to 60/200. Workers recovering but "
                    "there's a backlog of 600 messages. Scale worker-node to "
                    "clear it."
                )
            elif action.query_id == "4290":
                reward = -0.05
                feedback = (
                    "PID 4290 is a waiting query, not the lock holder. "
                    "The blocking lock is held by PID 4287."
                )
            else:
                reward = -0.05
                feedback = (
                    f"PID '{action.query_id}' not found. Check the database "
                    "logs — the blocking PID is 4287."
                )

        elif at == "scale_service":
            if not ts.killed_query:
                reward = -0.1
                feedback = (
                    "Scaling won't help — new workers will also get stuck "
                    "on the database lock. Kill the blocking query (PID 4287) "
                    "first."
                )
            elif action.service_name != "worker-node":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' doesn't need scaling. "
                    "Scale worker-node to drain the message backlog."
                )
            elif action.replicas < 4:
                reward = -0.1
                feedback = (
                    f"{action.replicas} replicas is not enough to drain the "
                    "backlog. Scale worker-node to at least 4 replicas."
                )
            elif ts.stabilized:
                feedback = "Already scaled. System is stable."
            else:
                ts.stabilized = True
                ts.services["worker-node"]["replicas"] = action.replicas
                ts.services["worker-node"]["status"] = "healthy"
                ts.services["worker-node"]["healthy_replicas"] = action.replicas
                ts.services["worker-node"]["cpu"] = 45.0
                ts.services["api-gateway"]["status"] = "healthy"
                ts.services["api-gateway"]["error_rate"] = 0.5
                ts.services["cache-layer"]["status"] = "healthy"
                ts.services["cache-layer"]["hit_rate"] = 85.0
                ts.metrics["queue_depth"] = 0
                ts.metrics["error_rate_percent"] = 0.5
                ts.metrics["latency_p99_ms"] = 80
                ts.metrics["cpu_percent"] = 45.0
                ts.alerts = []
                reward = 0.3
                feedback = (
                    f"Scaled worker-node to {action.replicas} replicas. "
                    "Backlog cleared, error rate 0.5%, latency 80ms. "
                    "All services healthy — incident resolved!"
                )
                ts.done = True

        elif at == "rollback_deployment":
            reward = -0.15
            feedback = (
                "RED HERRING: The config change (thread pool 50→100) was not "
                "the root cause. Rolling back won't help — the database lock "
                "is independent of the thread pool setting. Check database logs."
            )

        elif at == "restart_service":
            if not ts.killed_query:
                reward = -0.1
                feedback = (
                    "Restarting won't help — the database lock is still active. "
                    "New pods will immediately block on the same lock."
                )
            else:
                reward = -0.05
                feedback = "Not needed — scale worker-node instead to clear the backlog."

        elif at == "rotate_certs":
            reward = -0.1
            feedback = "No certificate issues. This is a database lock problem."

        elif at == "resolve_incident":
            if not ts.killed_query:
                reward = -0.2
                feedback = (
                    "Cannot resolve — database lock is still active and "
                    f"error rate is {ts.metrics['error_rate_percent']}%."
                )
            elif not ts.stabilized:
                reward = -0.1
                feedback = (
                    "Lock is cleared but workers are still recovering with "
                    "a backlog of 600 messages. Scale worker-node first."
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints
        if not ts.queried_api_gateway_logs and ts.step_count >= 2:
            hint = "Hint: Start by checking api-gateway logs to understand the 504 timeouts."
        elif (
            ts.queried_api_gateway_logs
            and not ts.queried_worker_logs
            and ts.step_count >= 4
        ):
            hint = "Hint: The api-gateway pointed to worker-node issues. Check worker-node logs."
        elif (
            ts.queried_worker_logs
            and not ts.queried_db_logs
            and ts.step_count >= 6
        ):
            hint = "Hint: Workers are stuck on DB queries. Check database logs for locks."
        elif ts.queried_db_logs and not ts.killed_query and ts.step_count >= 8:
            hint = "Hint: PID 4287 is the blocking query. Use kill_query(query_id='4287')."

        return reward, feedback, hint

    # ==================================================================
    # Task 4 — The Silent OOM (Memory Leak)
    # ==================================================================

    def _step_memory_leak(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation — memory keeps climbing
        if not ts.rolled_back_payment:
            ts.metrics["memory_percent"] = min(
                99.0, ts.metrics["memory_percent"] + 2.0
            )
            ts.services["payment-service"]["memory_percent"] = ts.metrics["memory_percent"]
            if ts.metrics["memory_percent"] >= 98.0:
                ts.services["payment-service"]["healthy_replicas"] = 0
                ts.services["payment-service"]["status"] = "crash_loop"
                ts.metrics["error_rate_percent"] = min(
                    50.0, ts.metrics["error_rate_percent"] + 5.0
                )

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                if svc == "payment-service" and not ts.queried_payment_logs:
                    ts.queried_payment_logs = True
                    ts.identified_leak = True
                    reward = 0.3
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "ROOT CAUSE IDENTIFIED: ProductCatalogCache in v4.1.0 has no "
                        "eviction policy. Cache grows ~50MB every 10 minutes until OOM. "
                        "Rollback to pre-v4.1.0 or restart with cache disabled."
                    )
                elif svc == "api-gateway" and not ts.queried_api_gw_logs_ml:
                    ts.queried_api_gw_logs_ml = True
                    reward = 0.05
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "API gateway sees 502s when payment-service pods restart. "
                        "The issue is in payment-service, not here."
                    )
                else:
                    feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed or no new information)"
            else:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )

        elif at == "restart_service":
            if action.service_name == "payment-service":
                if not ts.restarted_payment:
                    ts.restarted_payment = True
                    reward = 0.1
                    # Temporarily fix memory but it will climb again
                    ts.metrics["memory_percent"] = 45.0
                    ts.services["payment-service"]["memory_percent"] = 45.0
                    ts.services["payment-service"]["healthy_replicas"] = 3
                    ts.services["payment-service"]["status"] = "running"
                    ts.services["payment-service"]["restarts"] = 7
                    feedback = (
                        "Payment-service restarted — memory dropped to 45%, all 3 pods healthy. "
                        "BUT: the leak will return in ~20 minutes unless v4.1.0 "
                        "(with the broken cache) is rolled back."
                    )
                else:
                    reward = -0.05
                    feedback = (
                        "Already restarted. Restarting again is a band-aid — "
                        "the ProductCatalogCache leak will return. Roll back to v4.0.2."
                    )
            else:
                reward = -0.05
                feedback = f"'{action.service_name}' doesn't need a restart. The issue is in payment-service."

        elif at == "scale_service":
            if action.service_name == "payment-service":
                reward = -0.15
                feedback = (
                    "WRONG APPROACH: Scaling a leaking service just creates more "
                    "pods that will all OOM. The fix is to roll back the code that "
                    "introduced the unbounded cache (v4.1.0)."
                )
            else:
                reward = -0.05
                feedback = f"Scaling '{action.service_name}' won't help — the issue is a memory leak in payment-service."

        elif at == "rollback_deployment":
            if action.service_name != "payment-service":
                reward = -0.1
                feedback = f"'{action.service_name}' doesn't need a rollback. Roll back payment-service."
            elif action.version not in ("v4.0.2", "v4.0.1", "v4.0.0"):
                reward = -0.1
                feedback = (
                    f"Version '{action.version}' is not a valid rollback target. "
                    "The last version without the cache feature is v4.0.2."
                )
            elif ts.rolled_back_payment:
                feedback = "Already rolled back. The fix is in place."
            else:
                ts.rolled_back_payment = True
                ts.deployment_version = action.version
                ts.services["payment-service"]["version"] = action.version
                ts.services["payment-service"]["status"] = "healthy"
                ts.services["payment-service"]["memory_percent"] = 40.0
                ts.services["payment-service"]["healthy_replicas"] = 3
                ts.services["payment-service"]["restarts"] = 0
                ts.services["api-gateway"]["status"] = "healthy"
                ts.services["api-gateway"]["error_rate"] = 0.2
                ts.metrics["memory_percent"] = 40.0
                ts.metrics["error_rate_percent"] = 0.2
                ts.metrics["latency_p99_ms"] = 120
                ts.alerts = []
                reward = 0.5
                feedback = (
                    f"Rolled back payment-service to {action.version}. "
                    "ProductCatalogCache removed, memory stable at 40%, "
                    "all pods healthy. Incident resolved!"
                )
                ts.done = True

        elif at == "resolve_incident":
            if not ts.rolled_back_payment:
                reward = -0.2
                feedback = (
                    "Cannot resolve — the memory leak is still present. "
                    f"Memory at {ts.metrics['memory_percent']}%. "
                    "Roll back payment-service to remove the leaking cache."
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        elif at == "kill_query":
            reward = -0.1
            feedback = "No database lock detected. This is a memory leak issue, not a DB problem."

        elif at == "rotate_certs":
            reward = -0.1
            feedback = "No certificate issues detected. This is a memory leak in payment-service."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints
        if ts.step_count >= 2 and not ts.queried_payment_logs:
            hint = "Hint: Check payment-service logs to understand why pods keep OOM-killing."
        elif ts.step_count >= 4 and ts.identified_leak and not ts.rolled_back_payment:
            hint = (
                "Hint: The logs show ProductCatalogCache from v4.1.0 has no eviction. "
                "Roll back payment-service to v4.0.2 to remove the leaking cache."
            )
        elif ts.step_count >= 6 and ts.restarted_payment and not ts.rolled_back_payment:
            hint = (
                "Hint: Restarting is temporary — the cache will fill again. "
                "Roll back to v4.0.2 for a permanent fix."
            )

        ts.uptime = max(85.0, ts.uptime - 0.3)
        return reward, feedback, hint

    # ==================================================================
    # Task 5 — The Midnight Expiry (Certificate Expiry)
    # ==================================================================

    def _step_cert_expiry(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation until certs rotated
        if not ts.rotated_certs:
            ts.metrics["error_rate_percent"] = min(
                99.0, ts.metrics["error_rate_percent"] + 1.0
            )
            ts.metrics["queue_depth"] = min(
                5000, ts.metrics["queue_depth"] + 200
            )
            ts.uptime = max(40.0, ts.uptime - 1.5)

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc not in ts.logs:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )
            elif svc == "api-gateway" and not ts.queried_api_gw_logs_ce:
                ts.queried_api_gw_logs_ce = True
                reward = 0.05
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "TLS handshake failures everywhere. The v5.0.0 deploy looks suspicious "
                    "but the changelog says it's just a dependency bump. "
                    "Investigate payment-service or service-mesh-proxy for cert details."
                )
            elif svc == "payment-service" and not ts.queried_payment_logs_ce:
                ts.queried_payment_logs_ce = True
                reward = 0.05
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "mTLS client certificates are being rejected — cert expired. "
                    "Payment-service code is healthy. Check service-mesh-proxy for cert status."
                )
            elif svc == "worker-node" and not ts.queried_worker_logs_ce:
                ts.queried_worker_logs_ce = True
                reward = 0.05
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "All downstream TLS calls failing. Issue is in transport layer, not application. "
                    "Check service-mesh-proxy."
                )
            elif svc == "database" and not ts.queried_db_logs_ce:
                ts.queried_db_logs_ce = True
                reward = 0.05
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "Database engine is fine, but SSL client connections failing. "
                    "Cert issued by service-mesh CA — investigate service-mesh-proxy."
                )
            elif svc == "service-mesh-proxy" and not ts.queried_mesh_logs:
                ts.queried_mesh_logs = True
                ts.identified_cert_issue = True
                reward = 0.2
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "ROOT CAUSE FOUND: The mTLS certificate expired at 2026-04-05T00:00:00Z. "
                    "It was valid for 365 days (issued 2025-04-05). Automated rotation "
                    "failed because the Vault token expired. Manual rotation required: "
                    "use rotate_certs action."
                )
            elif svc == "load-balancer" and not ts.queried_lb_logs:
                ts.queried_lb_logs = True
                feedback = (
                    f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                    "Load balancer is healthy — CPU spike is from TLS retry storms, "
                    "not an LB issue. Fix the certificate and retries will stop."
                )
            else:
                feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed)"

        elif at == "rotate_certs":
            if ts.rotated_certs:
                feedback = "Certificates already rotated. Restart affected services to pick up new certs."
            elif not ts.identified_cert_issue:
                # Still allow it to work even without diagnosis, but penalise
                ts.rotated_certs = True
                ts.identified_cert_issue = True
                ts.services["service-mesh-proxy"]["cert_status"] = "VALID"
                ts.services["service-mesh-proxy"]["cert_expiry"] = "2027-04-05T00:00:00Z"
                reward = -0.05
                feedback = (
                    "Rotating certs blindly — it worked, but you should diagnose before acting. "
                    "New cert valid until 2027-04-05. "
                    "Services are still using cached expired certs. "
                    "Restart api-gateway, payment-service, and worker-node to load new certs."
                )
            else:
                ts.rotated_certs = True
                ts.services["service-mesh-proxy"]["cert_status"] = "VALID"
                ts.services["service-mesh-proxy"]["cert_expiry"] = "2027-04-05T00:00:00Z"
                reward = 0.3
                feedback = (
                    "Certificates rotated successfully! New cert valid until 2027-04-05. "
                    "Services are still using cached expired certs in memory. "
                    "Restart api-gateway, payment-service, and worker-node to load the new certs."
                )

        elif at == "restart_service":
            if not ts.rotated_certs:
                reward = -0.1
                feedback = (
                    f"Restarting '{action.service_name}' won't help — the certs are "
                    "expired. Restarted services will just load the same expired cert. "
                    "Rotate the certificates first."
                )
            elif action.service_name in ("api-gateway", "payment-service", "worker-node"):
                if action.service_name in ts.restarted_services:
                    feedback = f"'{action.service_name}' already restarted with new certs."
                else:
                    ts.restarted_services.add(action.service_name)
                    svc_data = ts.services[action.service_name]
                    svc_data["status"] = "healthy"
                    svc_data["error_rate"] = 0.5
                    if "tls_errors" in svc_data:
                        svc_data["tls_errors"] = 0

                    restarted = len(ts.restarted_services)
                    needed = {"api-gateway", "payment-service", "worker-node"}
                    remaining = needed - ts.restarted_services

                    if remaining:
                        reward = 0.1
                        feedback = (
                            f"Restarted {action.service_name} — loaded new certs, TLS healthy. "
                            f"Still need to restart: {', '.join(sorted(remaining))}"
                        )
                    else:
                        reward = 0.15
                        # All services restarted — full recovery
                        ts.services["database"]["connections"] = 120
                        ts.services["database"]["ssl_status"] = "connected"
                        ts.services["database"]["status"] = "healthy"
                        ts.services["load-balancer"]["cpu"] = 35.0
                        ts.services["load-balancer"]["status"] = "healthy"
                        ts.services["load-balancer"]["tls_retry_rate"] = "0/min"
                        ts.services["cache-layer"]["hit_rate"] = 88.0
                        ts.metrics["error_rate_percent"] = 0.5
                        ts.metrics["latency_p99_ms"] = 120
                        ts.metrics["cpu_percent"] = 40.0
                        ts.metrics["queue_depth"] = 0
                        ts.metrics["db_connections"] = 120
                        ts.alerts = []
                        feedback = (
                            f"Restarted {action.service_name} — all services now running "
                            "with valid certs. TLS errors cleared, connections restored, "
                            "error rate 0.5%. Incident resolved!"
                        )
                        ts.done = True
            else:
                reward = -0.05
                feedback = (
                    f"'{action.service_name}' doesn't need a restart. "
                    "Restart api-gateway, payment-service, and worker-node."
                )

        elif at == "rollback_deployment":
            # Red herring — rolling back v5.0.0 won't fix the cert
            if action.service_name == "api-gateway" and action.version in ("v4.9.0", "v4.8.0"):
                if ts.rolled_back_deploy_ce:
                    feedback = "Already rolled back. The issue persists — this was not the cause."
                else:
                    ts.rolled_back_deploy_ce = True
                    reward = -0.15
                    ts.services["api-gateway"]["version"] = action.version
                    feedback = (
                        f"Rolled back api-gateway to {action.version}. "
                        "TLS errors PERSIST — the v5.0.0 deploy was not the cause. "
                        "The issue is an expired mTLS certificate, not a code change. "
                        "Check service-mesh-proxy logs."
                    )
            else:
                reward = -0.1
                feedback = (
                    "Rollback won't fix this. The TLS errors are caused by an expired "
                    "certificate, not a bad deployment. Investigate service-mesh-proxy."
                )

        elif at == "scale_service":
            reward = -0.1
            feedback = (
                "Scaling won't fix TLS certificate errors. Every new pod will "
                "also fail the TLS handshake. Fix the certificate first."
            )

        elif at == "kill_query":
            reward = -0.1
            feedback = "No database lock issues. This is a TLS certificate problem."

        elif at == "resolve_incident":
            if not ts.rotated_certs:
                reward = -0.2
                feedback = (
                    "Cannot resolve — TLS errors at "
                    f"{ts.metrics['error_rate_percent']}%. "
                    "Certs have not been rotated."
                )
            elif len(ts.restarted_services) < 3:
                needed = {"api-gateway", "payment-service", "worker-node"}
                remaining = needed - ts.restarted_services
                reward = -0.1
                feedback = (
                    "Certs rotated but services still using cached expired certs. "
                    f"Restart: {', '.join(sorted(remaining))}"
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints (progressive, delayed)
        if ts.step_count >= 3 and not ts.queried_mesh_logs and not ts.identified_cert_issue:
            if ts.queried_api_gw_logs_ce or ts.queried_payment_logs_ce:
                hint = (
                    "Hint: Multiple services mention TLS/cert issues. "
                    "Check service-mesh-proxy logs — it manages all mTLS certificates."
                )
            else:
                hint = "Hint: Start by checking logs. The TLS errors suggest a certificate problem."
        elif ts.step_count >= 5 and ts.rolled_back_deploy_ce and not ts.identified_cert_issue:
            hint = (
                "Hint: The rollback didn't help — this isn't a code issue. "
                "Check service-mesh-proxy for certificate status."
            )
        elif ts.step_count >= 6 and ts.identified_cert_issue and not ts.rotated_certs:
            hint = "Hint: The mTLS cert is expired. Use rotate_certs to issue a new certificate."
        elif ts.step_count >= 8 and ts.rotated_certs and len(ts.restarted_services) < 3:
            needed = {"api-gateway", "payment-service", "worker-node"}
            remaining = needed - ts.restarted_services
            hint = (
                f"Hint: Certs rotated, but services need restart to load new certs. "
                f"Restart: {', '.join(sorted(remaining))}"
            )

        return reward, feedback, hint

    # ------------------------------------------------------------------
    # Observation builder
    # ------------------------------------------------------------------

    def _build_observation(
        self,
        reward: Optional[float],
        feedback: str = "",
        hint: str = "",
    ) -> SREObservation:
        ts = self._ts
        if ts is None:
            return SREObservation(done=True, reward=0.0, feedback=feedback)

        cfg = TASK_CONFIGS[ts.task_id]
        return SREObservation(
            done=ts.done,
            reward=reward,
            active_alerts=list(ts.alerts),
            system_metrics=dict(ts.metrics),
            queried_logs="",
            cloud_cost_usd=round(ts.cloud_cost, 2),
            uptime_percentage=round(ts.uptime, 2),
            task_id=ts.task_id,
            difficulty=ts.difficulty,
            feedback=feedback,
            hint=hint,
            current_deployment_version=ts.deployment_version,
            services=copy.deepcopy(ts.services),
            attempt_number=ts.step_count,
            max_attempts=ts.max_attempts,
            metadata={
                "score": _normalised_score(ts.difficulty, ts.cumulative_reward),
                "cumulative_reward": round(ts.cumulative_reward, 4),
            },
        )
