// The live page: one button, one stream. Events are the Flow's own log lines; nothing is computed here.
(() => {
  const panel = document.getElementById("live");
  if (!panel) return;
  const button = document.getElementById("live-start");
  const note = document.getElementById("live-note");
  const log = document.getElementById("live-log");
  const pill = document.getElementById("live-status");
  const facts = {
    run: document.getElementById("fact-run"),
    started: document.getElementById("fact-started"),
    result: document.getElementById("fact-result"),
    cost: document.getElementById("fact-cost"),
  };
  let source = null;

  const line = (event) => {
    const { ts, step, status, ...rest } = event;
    const detail = Object.entries(rest).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ");
    return `${(ts || "").slice(11, 19)} ${String(step).padEnd(18)} ${String(status).padEnd(5)} ${detail}`.trimEnd();
  };

  const show = (snap) => {
    pill.textContent = snap.status;
    pill.dataset.status = snap.status;
    panel.dataset.status = snap.status;
    facts.run.textContent = snap.run_id || "—";
    facts.started.textContent = snap.started_at || "—";
    facts.result.textContent = snap.result || snap.error || "—";
    facts.cost.textContent = snap.cost_usd != null ? `$${snap.cost_usd.toFixed(4)}` : "—";
    button.disabled = snap.status === "running";
  };

  const refresh = async () => {
    const res = await fetch("/live/status");
    if (!res.ok) return null;
    const snap = await res.json();
    show(snap);
    return snap;
  };

  const follow = (runId) => {
    if (source) source.close();
    log.textContent = "";
    source = new EventSource(`/live/events?run_id=${encodeURIComponent(runId)}`);
    source.onmessage = (m) => {
      try {
        log.textContent += line(JSON.parse(m.data)) + "\n";
      } catch {
        log.textContent += m.data + "\n";
      }
      log.scrollTop = log.scrollHeight;
    };
    source.addEventListener("end", () => {
      source.close();
      source = null;
      refresh().then((snap) => {
        note.textContent = snap && snap.status === "done" ? `Finished: ${snap.result}.` : "The run stopped.";
      });
    });
    source.onerror = () => {
      note.textContent = "The stream dropped; reconnecting…";
    };
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    note.textContent = "Starting…";
    const res = await fetch("/live/start", { method: "POST" });
    const data = await res.json();
    if (res.status === 409) {
      note.textContent = data.error;
      follow(data.run_id);
      return refresh();
    }
    if (!res.ok) {
      note.textContent = data.error || `The server answered ${res.status}.`;
      button.disabled = false;
      return;
    }
    note.textContent = "Running. Crew 1 takes about four minutes, Crew 2 about five.";
    await refresh();
    follow(data.run_id);
  });

  refresh().then((snap) => {
    if (snap && snap.run_id) follow(snap.run_id);
  });
})();
