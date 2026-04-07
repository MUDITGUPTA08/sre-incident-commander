"""FastAPI application wiring for SRE Incident Commander environment."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from openenv.core.env_server import create_fastapi_app

try:
    from ..models import SREAction, SREObservation
except ImportError:
    from models import SREAction, SREObservation

try:
    from .environment import SREIncidentEnvironment, TASK_CONFIGS
except ImportError:
    from environment import SREIncidentEnvironment, TASK_CONFIGS

app = create_fastapi_app(
    env=SREIncidentEnvironment,
    action_cls=SREAction,
    observation_cls=SREObservation,
    max_concurrent_envs=10,
)


@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SRE Incident Commander &mdash; OpenEnv Environment</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{
    background:#0d1117;color:#c9d1d9;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    line-height:1.6;padding:0;
  }
  a{color:#58a6ff;text-decoration:none}
  a:hover{text-decoration:underline}
  code,pre,.mono{font-family:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace}
  .container{max-width:1100px;margin:0 auto;padding:0 24px 64px}

  /* ---- HERO ---- */
  .hero{
    background:linear-gradient(135deg,#161b22 0%,#0d1117 50%,#161b22 100%);
    border-bottom:1px solid #21262d;padding:56px 24px 48px;text-align:center;
  }
  .hero h1{font-size:2.4rem;font-weight:800;color:#f0f6fc;letter-spacing:-0.02em}
  .hero .version{
    display:inline-block;background:#238636;color:#fff;
    font-size:.75rem;font-weight:600;padding:2px 10px;border-radius:12px;
    margin-left:10px;vertical-align:middle;
  }
  .hero p.desc{
    max-width:680px;margin:16px auto 0;font-size:1.05rem;color:#8b949e;
  }
  .hero .badges{margin-top:20px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
  .hero .badge{
    font-size:.75rem;padding:4px 12px;border-radius:6px;
    border:1px solid #30363d;color:#8b949e;background:#161b22;
  }

  /* ---- SECTION ---- */
  .section{margin-top:48px}
  .section-title{
    font-size:1.35rem;font-weight:700;color:#f0f6fc;
    margin-bottom:20px;padding-bottom:10px;border-bottom:1px solid #21262d;
  }
  .section-subtitle{font-size:.9rem;color:#8b949e;margin-bottom:16px}

  /* ---- TOPOLOGY ---- */
  .topology{
    background:#161b22;border:1px solid #30363d;border-radius:12px;
    padding:32px 24px;overflow-x:auto;
  }
  .topo-grid{
    display:flex;align-items:center;justify-content:center;
    gap:0;min-width:700px;position:relative;
  }
  .topo-node{
    background:#0d1117;border:2px solid #30363d;border-radius:10px;
    padding:14px 18px;text-align:center;min-width:120px;position:relative;
    transition:border-color .2s;
  }
  .topo-node:hover{border-color:#58a6ff}
  @keyframes pulse-red{0%,100%{box-shadow:0 0 0 0 rgba(248,81,73,0.4)}50%{box-shadow:0 0 12px 4px rgba(248,81,73,0.15)}}
  @keyframes pulse-green{0%,100%{box-shadow:0 0 0 0 rgba(46,160,67,0.4)}50%{box-shadow:0 0 12px 4px rgba(46,160,67,0.15)}}
  .topo-node.status-critical{border-color:#f85149;animation:pulse-red 2s ease-in-out infinite}
  .topo-node.status-healthy{border-color:#2ea043;animation:pulse-green 3s ease-in-out infinite}
  .topo-node .name{font-weight:700;font-size:.85rem;color:#f0f6fc}
  .topo-node .role{font-size:.7rem;color:#8b949e;margin-top:2px}
  .topo-arrow{
    color:#30363d;font-size:1.4rem;padding:0 6px;flex-shrink:0;
    display:flex;align-items:center;user-select:none;
  }
  .topo-side{
    display:flex;flex-direction:column;gap:10px;margin-left:32px;
  }
  .topo-side .topo-node{border-style:dashed}
  .topo-mesh-wrap{
    border:2px dashed #238636;border-radius:16px;padding:20px 16px;
    position:relative;
  }
  .topo-mesh-label{
    position:absolute;top:-11px;left:24px;background:#0d1117;
    padding:0 8px;font-size:.7rem;color:#238636;font-weight:600;
  }

  /* ---- TASK CARDS ---- */
  .task-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
  .task-card{
    background:#161b22;border:1px solid #30363d;border-radius:12px;
    padding:20px 22px;transition:border-color .2s;
  }
  .task-card:hover{border-color:#58a6ff}
  .task-card .card-head{display:flex;align-items:center;gap:10px;margin-bottom:10px}
  .task-card .card-title{font-weight:700;font-size:1rem;color:#f0f6fc}
  .diff-badge{
    font-size:.65rem;font-weight:700;padding:2px 9px;border-radius:10px;
    text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;
  }
  .diff-easy{background:#23863622;color:#3fb950;border:1px solid #23863655}
  .diff-medium{background:#d2992222;color:#d29922;border:1px solid #d2992255}
  .diff-medium-hard{background:#db611322;color:#db6113;border:1px solid #db611355}
  .diff-hard{background:#f8514922;color:#f85149;border:1px solid #f8514955}
  .diff-expert{background:#a371f722;color:#a371f7;border:1px solid #a371f755}
  .diff-nightmare{background:#f4212222;color:#ff6b6b;border:1px solid #f4212255;text-transform:uppercase;letter-spacing:0.05em}
  .task-card .card-desc{font-size:.88rem;color:#8b949e;margin-bottom:12px}
  .task-card .card-meta{font-size:.78rem;color:#6e7681}
  .task-card .optimal{
    margin-top:12px;padding:10px 14px;background:#0d1117;
    border-radius:8px;font-size:.8rem;color:#8b949e;
  }
  .task-card .optimal strong{color:#c9d1d9}
  .optimal ol{margin:6px 0 0 18px;padding:0}
  .optimal li{margin-bottom:2px}

  /* ---- TABLE ---- */
  .action-table{
    width:100%;border-collapse:collapse;background:#161b22;
    border:1px solid #30363d;border-radius:12px;overflow:hidden;
    font-size:.88rem;
  }
  .action-table th{
    background:#0d1117;color:#f0f6fc;font-weight:600;
    text-align:left;padding:12px 16px;border-bottom:1px solid #30363d;
  }
  .action-table td{
    padding:10px 16px;border-bottom:1px solid #21262d;color:#c9d1d9;
    vertical-align:top;
  }
  .action-table tr:last-child td{border-bottom:none}
  .action-table code{
    background:#0d1117;padding:2px 6px;border-radius:4px;
    font-size:.82rem;color:#79c0ff;
  }

  /* ---- FEATURES ---- */
  .feature-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
  .feature-card{
    background:#161b22;border:1px solid #30363d;border-radius:10px;
    padding:16px 18px;
  }
  .feature-card .ft-icon{font-size:1.2rem;margin-bottom:6px}
  .feature-card .ft-title{font-weight:700;font-size:.88rem;color:#f0f6fc}
  .feature-card .ft-desc{font-size:.78rem;color:#8b949e;margin-top:4px}

  /* ---- TRY IT ---- */
  .try-block{
    background:#161b22;border:1px solid #30363d;border-radius:12px;
    padding:20px 24px;
  }
  .try-block pre{
    background:#0d1117;border:1px solid #21262d;border-radius:8px;
    padding:14px 18px;overflow-x:auto;font-size:.82rem;color:#79c0ff;
    margin-bottom:12px;
  }
  .try-block pre:last-child{margin-bottom:0}
  .try-label{font-size:.78rem;color:#8b949e;margin-bottom:6px;font-weight:600}

  /* ---- FOOTER ---- */
  .footer{
    margin-top:56px;padding:24px 0;border-top:1px solid #21262d;
    text-align:center;font-size:.82rem;color:#6e7681;
  }
  .footer a{color:#58a6ff}
</style>
</head>
<body>

<!-- HERO -->
<div class="hero">
  <h1>SRE Incident Commander <span class="version">v1.0.0</span></h1>
  <p class="desc">
    AI agent training environment for SRE incident response.
    Diagnose and resolve production infrastructure incidents across
    six escalating scenarios &mdash; from traffic spikes to cascading failures.
  </p>
  <div class="badges">
    <span class="badge">OpenEnv Compatible</span>
    <span class="badge">6 Tasks</span>
    <span class="badge">7 Actions</span>
    <span class="badge">Shaped Rewards</span>
    <span class="badge">No External Dependencies</span>
  </div>
</div>

<div class="container">

  <!-- SERVICE TOPOLOGY -->
  <div class="section">
    <div class="section-title">Service Topology</div>
    <p class="section-subtitle">Simulated microservice architecture used across all incident scenarios</p>
    <div class="topology">
      <div class="topo-mesh-wrap">
        <span class="topo-mesh-label">service-mesh-proxy (envoy sidecar &middot; mTLS)</span>
        <div class="topo-grid">
          <div class="topo-node status-healthy">
            <div class="name">load-balancer</div>
            <div class="role">L7 ingress</div>
          </div>
          <div class="topo-arrow">&rarr;</div>
          <div class="topo-node status-critical">
            <div class="name">api-gateway</div>
            <div class="role">routing + auth</div>
          </div>
          <div class="topo-arrow">&rarr;</div>
          <div class="topo-node status-critical">
            <div class="name">worker-node</div>
            <div class="role">queue consumer</div>
          </div>
          <div class="topo-arrow">&rarr;</div>
          <div class="topo-node status-critical">
            <div class="name">database</div>
            <div class="role">PostgreSQL</div>
          </div>
          <div class="topo-side">
            <div class="topo-node status-critical">
              <div class="name">payment-service</div>
              <div class="role">checkout + billing</div>
            </div>
            <div class="topo-node status-healthy">
              <div class="name">cache-layer</div>
              <div class="role">Redis</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- TASKS -->
  <div class="section">
    <div class="section-title">Incident Scenarios</div>
    <p class="section-subtitle">Six scenarios with escalating difficulty, red herrings, and trap actions</p>
    <div class="task-grid">

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Traffic Spike</span>
          <span class="diff-badge diff-easy">easy</span>
        </div>
        <div class="card-desc">
          Worker-node CPU at 92%, order queue backlog of 500 messages growing at 200/min.
          Scale workers to drain the queue before overflow.
        </div>
        <div class="card-meta">Max attempts: 10</div>
        <div class="optimal">
          <strong>Optimal path (2 steps):</strong>
          <ol>
            <li><code>scale_service</code> worker-node to 5+ replicas</li>
            <li><code>resolve_incident</code> once queue drains</li>
          </ol>
        </div>
      </div>

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Poison Pill</span>
          <span class="diff-badge diff-medium">medium</span>
        </div>
        <div class="card-desc">
          API error rate spiked to 15% after deployment v2.1.0.
          Diagnose the NullPointerException and roll back.
        </div>
        <div class="card-meta">Max attempts: 10</div>
        <div class="optimal">
          <strong>Optimal path (2 steps):</strong>
          <ol>
            <li><code>query_logs</code> api-gateway &rarr; find NPE in v2.1.0</li>
            <li><code>rollback_deployment</code> api-gateway to v2.0.9</li>
          </ol>
        </div>
      </div>

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Silent OOM</span>
          <span class="diff-badge diff-medium-hard">medium-hard</span>
        </div>
        <div class="card-desc">
          Payment-service pods keep OOM-killing every ~30 min.
          Identify the unbounded ProductCatalogCache in v4.1.0 and roll back.
        </div>
        <div class="card-meta">Max attempts: 12</div>
        <div class="optimal">
          <strong>Optimal path (2&ndash;3 steps):</strong>
          <ol>
            <li><code>query_logs</code> payment-service &rarr; find cache leak</li>
            <li><code>restart_service</code> payment-service (optional mitigation)</li>
            <li><code>rollback_deployment</code> payment-service to v4.0.2</li>
          </ol>
        </div>
      </div>

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Cascading Lock</span>
          <span class="diff-badge diff-hard">hard</span>
        </div>
        <div class="card-desc">
          Multiple services failing: 504s, CrashLoopBackOff, DB pool exhaustion.
          A config change and memory spike are red herrings &mdash; a 45-min DB lock is the root cause.
        </div>
        <div class="card-meta">Max attempts: 15</div>
        <div class="optimal">
          <strong>Optimal path (5 steps):</strong>
          <ol>
            <li><code>query_logs</code> api-gateway &rarr; worker timeouts</li>
            <li><code>query_logs</code> worker-node &rarr; DB queries hanging</li>
            <li><code>query_logs</code> database &rarr; find blocking PID</li>
            <li><code>kill_query</code> blocking PID</li>
            <li><code>scale_service</code> worker-node to 4+ replicas</li>
          </ol>
        </div>
      </div>

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Midnight Expiry</span>
          <span class="diff-badge diff-expert">expert</span>
        </div>
        <div class="card-desc">
          All inter-service communication failing with TLS handshake errors.
          A recent deploy is a red herring &mdash; the real cause is an expired mTLS
          certificate in the service mesh.
        </div>
        <div class="card-meta">Max attempts: 20</div>
        <div class="optimal">
          <strong>Optimal path (5&ndash;6 steps):</strong>
          <ol>
            <li><code>query_logs</code> service-mesh-proxy &rarr; find expired cert</li>
            <li><code>rotate_certs</code> to issue new mTLS cert</li>
            <li><code>restart_service</code> api-gateway</li>
            <li><code>restart_service</code> payment-service</li>
            <li><code>restart_service</code> worker-node</li>
          </ol>
        </div>
      </div>

      <div class="task-card">
        <div class="card-head">
          <span class="card-title">The Perfect Storm</span>
          <span class="diff-badge diff-nightmare">nightmare</span>
        </div>
        <div class="card-desc">
          Two simultaneous incidents: bad deployment causing 500 errors
          AND database connection leak. Agent must triage correctly &mdash;
          fix customer-facing errors first, then resolve the DB leak.
        </div>
        <div class="card-meta">Max attempts: 20</div>
        <div class="optimal">
          <strong>Optimal path (6 steps):</strong>
          <ol>
            <li><code>query_logs</code> api-gateway &rarr; see NPE + DB warnings</li>
            <li><code>query_logs</code> database &rarr; find leaking connections</li>
            <li><code>rollback_deployment</code> api-gateway to v5.9.2</li>
            <li><code>kill_query</code> leaking PID</li>
            <li><code>scale_service</code> worker-node to clear backlog</li>
            <li><code>resolve_incident</code></li>
          </ol>
        </div>
      </div>

    </div>
  </div>

  <!-- DIFFICULTY PROGRESSION CHART -->
  <div class="section">
    <div class="section-title">Difficulty Progression</div>
    <p class="section-subtitle">Llama 3.3 70B scores across tasks &mdash; harder tasks produce lower, more varied scores</p>
    <div style="margin-top:20px;display:flex;flex-direction:column;gap:12px">

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">easy</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:100%;height:100%;background:linear-gradient(90deg,#238636,#2ea043);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">1.00</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">medium</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:100%;height:100%;background:linear-gradient(90deg,#238636,#2ea043);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">1.00</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">medium-hard</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:97%;height:100%;background:linear-gradient(90deg,#2ea043,#d29922);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">0.97</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">hard</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:97%;height:100%;background:linear-gradient(90deg,#d29922,#db6d28);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">0.97</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">expert</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:97%;height:100%;background:linear-gradient(90deg,#db6d28,#f85149);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">0.97</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="width:130px;text-align:right;color:#8b949e;font-size:.85rem">nightmare</span>
        <div style="flex:1;background:#161b22;border-radius:6px;height:28px;border:1px solid #21262d;overflow:hidden">
          <div style="width:95%;height:100%;background:linear-gradient(90deg,#f85149,#da3633);border-radius:5px;display:flex;align-items:center;padding-left:10px">
            <span class="mono" style="font-size:.75rem;color:#fff;font-weight:600">0.95</span>
          </div>
        </div>
      </div>

    </div>
    <p style="margin-top:12px;font-size:.8rem;color:#484f58">Tested with Llama 3.3 70B via Groq API. Scores vary by run due to surface randomization. Average: 0.978 across all 6 tasks.</p>
  </div>

  <!-- LLM BASELINE RESULTS -->
  <div class="section">
    <div class="section-title">LLM Baseline Results</div>
    <p class="section-subtitle">Llama 3.3 70B (via Groq) &mdash; all 6 tasks, average score <strong style="color:#2ea043">0.978</strong></p>
    <table class="action-table" style="margin-top:16px">
      <thead>
        <tr><th>Task</th><th>Difficulty</th><th>Steps</th><th>Score</th><th>Highlights</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><code>easy</code></td><td><span class="diff-badge diff-easy">easy</span></td>
          <td>4</td><td style="color:#2ea043;font-weight:700">1.000</td>
          <td>Scaled workers progressively, queue auto-resolved</td>
        </tr>
        <tr>
          <td><code>medium</code></td><td><span class="diff-badge diff-medium">medium</span></td>
          <td>2</td><td style="color:#2ea043;font-weight:700">1.000</td>
          <td>Perfect play &mdash; queried logs, rolled back v2.0.9</td>
        </tr>
        <tr>
          <td><code>hard</code></td><td><span class="diff-badge diff-hard">hard</span></td>
          <td>4</td><td style="color:#2ea043;font-weight:700">0.973</td>
          <td>Found randomised PID 9526 from logs, killed lock</td>
        </tr>
        <tr>
          <td><code>memory_leak</code></td><td><span class="diff-badge diff-medium-hard">medium-hard</span></td>
          <td>2</td><td style="color:#2ea043;font-weight:700">0.972</td>
          <td>Diagnosed heap dump, rolled back to v4.0.2</td>
        </tr>
        <tr>
          <td><code>cert_expiry</code></td><td><span class="diff-badge diff-expert">expert</span></td>
          <td>5</td><td style="color:#2ea043;font-weight:700">0.970</td>
          <td>Skipped red herrings, straight to mesh-proxy</td>
        </tr>
        <tr>
          <td><code>perfect_storm</code></td><td><span class="diff-badge diff-nightmare">nightmare</span></td>
          <td>5</td><td style="color:#d29922;font-weight:700">0.950</td>
          <td>Correct triage: rollback &rarr; kill leak &rarr; scale</td>
        </tr>
      </tbody>
    </table>
    <p style="margin-top:10px;font-size:.8rem;color:#484f58">Zero negative rewards &mdash; LLM avoided all trap actions. Randomised PIDs confirmed working (9526, 4014).</p>
  </div>

  <!-- ACTION SPACE -->
  <div class="section">
    <div class="section-title">Action Space</div>
    <p class="section-subtitle">Seven discrete actions available to the agent at every step</p>
    <table class="action-table">
      <thead>
        <tr><th>Action</th><th>Parameters</th><th>Description</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><code>scale_service</code></td>
          <td><code>service_name</code>, <code>replicas</code></td>
          <td>Horizontally scale a service to the specified replica count</td>
        </tr>
        <tr>
          <td><code>rollback_deployment</code></td>
          <td><code>service_name</code>, <code>version</code></td>
          <td>Roll back a service to a previous deployment version</td>
        </tr>
        <tr>
          <td><code>query_logs</code></td>
          <td><code>service_name</code></td>
          <td>Retrieve recent logs for a service (diagnostic, no side effects)</td>
        </tr>
        <tr>
          <td><code>kill_query</code></td>
          <td><code>query_id</code></td>
          <td>Terminate a long-running or locked database query by PID</td>
        </tr>
        <tr>
          <td><code>restart_service</code></td>
          <td><code>service_name</code></td>
          <td>Rolling restart of all pods for a service</td>
        </tr>
        <tr>
          <td><code>rotate_certs</code></td>
          <td>&mdash;</td>
          <td>Rotate mTLS certificates via the service mesh CA</td>
        </tr>
        <tr>
          <td><code>resolve_incident</code></td>
          <td>&mdash;</td>
          <td>Declare the incident resolved (fails if root cause not fixed)</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- KEY FEATURES -->
  <div class="section">
    <div class="section-title">Key Features</div>
    <div class="feature-grid">
      <div class="feature-card">
        <div class="ft-title">Randomisation</div>
        <div class="ft-desc">PIDs, alert ordering, and metric noise are randomised each episode to prevent memorisation.</div>
      </div>
      <div class="feature-card">
        <div class="ft-title">Efficiency Scoring</div>
        <div class="ft-desc">Normalised 0&ndash;1 score rewards faster resolution. Fewer steps = higher score.</div>
      </div>
      <div class="feature-card">
        <div class="ft-title">Timeline &amp; Post-mortem</div>
        <div class="ft-desc">Full action timeline with timestamps, rewards, and outcomes for every episode.</div>
      </div>
      <div class="feature-card">
        <div class="ft-title">Shaped Rewards</div>
        <div class="ft-desc">Incremental positive rewards for correct diagnostic steps, penalties for wrong actions.</div>
      </div>
      <div class="feature-card">
        <div class="ft-title">Trap Actions</div>
        <div class="ft-desc">Scaling a buggy service, killing victim PIDs, or restarting before cert rotation all penalise.</div>
      </div>
    </div>
  </div>

  <!-- TRY IT LIVE -->
  <div class="section">
    <div class="section-title">Try It Live</div>
    <p class="section-subtitle">Click to run a real episode against this environment &mdash; or use curl</p>
    <div class="try-block">
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
        <select id="task-select" style="background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-family:inherit;font-size:.85rem">
          <option value="easy">easy &mdash; The Traffic Spike</option>
          <option value="medium">medium &mdash; The Poison Pill</option>
          <option value="memory_leak">memory_leak &mdash; The Silent OOM</option>
          <option value="hard">hard &mdash; The Cascading Lock</option>
          <option value="cert_expiry">cert_expiry &mdash; The Midnight Expiry</option>
          <option value="perfect_storm">perfect_storm &mdash; The Perfect Storm</option>
        </select>
        <button id="try-btn" onclick="tryReset()" style="background:#238636;color:#fff;border:none;border-radius:6px;padding:8px 20px;font-weight:600;font-size:.85rem;cursor:pointer;transition:background .2s">
          Reset Episode
        </button>
      </div>
      <pre id="try-output" style="max-height:300px;overflow-y:auto;font-size:.78rem;color:#8b949e">Click "Reset Episode" to see the initial observation...</pre>

      <div class="try-label" style="margin-top:20px">Or use curl:</div>
      <pre>curl -X POST /reset -H "Content-Type: application/json" -d '{"task_id": "easy"}'
curl -X POST /step  -H "Content-Type: application/json" -d '{"action_type": "scale_service", "service_name": "worker-node", "replicas": 5}'</pre>

      <div class="try-label">Endpoints:</div>
      <pre>GET  /health    GET  /tasks     GET  /state
POST /reset     POST /step      WS   /ws</pre>
    </div>
  </div>

  <!-- FOOTER -->
  <div class="footer">
    <p>
      <strong>SRE Incident Commander</strong> &mdash; an
      <a href="https://github.com/meta-pytorch/OpenEnv" target="_blank" rel="noopener">OpenEnv</a>
      environment for the
      <a href="https://huggingface.co/spaces/muditgupta08/sre-incident-commander" target="_blank" rel="noopener">Hugging Face Spaces</a>
      + Meta PyTorch Hackathon.
    </p>
    <p style="margin-top:6px">
      <a href="https://github.com/MUDITGUPTA08/Triage" target="_blank" rel="noopener">Source Code</a>
      &nbsp;&middot;&nbsp; Built with FastAPI &amp; pure Python &nbsp;&middot;&nbsp;
      103 tests &nbsp;&middot;&nbsp; Zero external dependencies
    </p>
  </div>

<script>
async function tryReset(){
  var btn=document.getElementById('try-btn');
  var out=document.getElementById('try-output');
  var task=document.getElementById('task-select').value;
  btn.disabled=true;btn.textContent='Loading...';btn.style.background='#30363d';
  out.textContent='Sending POST /reset ...';
  try{
    var resp=await fetch('/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:task})});
    var data=await resp.json();
    out.textContent=JSON.stringify(data,null,2);
    out.style.color='#c9d1d9';
  }catch(e){
    out.textContent='Error: '+e.message;out.style.color='#f85149';
  }finally{
    btn.disabled=false;btn.textContent='Reset Episode';btn.style.background='#238636';
  }
}
</script>

</div>
</body>
</html>"""


@app.get("/tasks")
def list_tasks():
    return [
        {
            "id": cfg["id"],
            "name": cfg["name"],
            "difficulty": cfg["difficulty"],
            "description": cfg["description"],
            "max_attempts": cfg["max_attempts"],
        }
        for cfg in TASK_CONFIGS.values()
    ]


def main(host: str = "0.0.0.0", port: int = 7860):
    """Entry point for uv run or python -m."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
