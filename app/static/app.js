// The break-it panel. One fetch, one verdict, one polite announcement.
(() => {
  const stamp = document.getElementById("stamp");
  const panel = document.getElementById("verdict");
  const rows = document.getElementById("verdict-rows");
  const count = document.getElementById("verdict-count");
  const title = document.getElementById("verdict-title");
  const live = document.getElementById("verdict-live");
  const faults = Array.from(document.querySelectorAll(".fault"));
  const form = document.getElementById("upload-form");
  if (!panel || !rows) return;

  const setStamp = (passed) => {
    if (!stamp) return;
    stamp.dataset.verdict = passed ? "accepted" : "refused";
    stamp.textContent = passed ? "Accepted" : "Refused";
    stamp.dataset.changed = "1";
    stamp.addEventListener("animationend", () => delete stamp.dataset.changed, { once: true });
  };

  const cell = (text, className) => {
    const td = document.createElement("td");
    td.textContent = text || "";
    if (className) td.className = className;
    return td;
  };

  const render = (data, label) => {
    const failures = (data.checks || []).filter((c) => !c.passed);
    rows.replaceChildren();
    for (const c of failures) {
      const tr = document.createElement("tr");
      tr.className = "is-failed";
      tr.append(cell(c.name, "check-name"), cell(c.column || "—"), cell(c.message), cell(c.hint || "", "hint"));
      rows.append(tr);
    }
    if (!failures.length) {
      const tr = document.createElement("tr");
      const td = cell("Every check passed. This file may be handed to the modelling crew.");
      td.colSpan = 4;
      tr.append(td);
      rows.append(tr);
    }
    title.textContent = data.passed ? `Accepted: ${label}` : `Refused: ${label}`;
    count.textContent = `${data.n_checks - data.n_failed} of ${data.n_checks} checks passed`;
    panel.hidden = false;
    setStamp(data.passed);
    live.textContent = data.passed
      ? `Accepted. ${data.n_checks} checks passed.`
      : `Refused. ${data.n_failed} of ${data.n_checks} checks failed: ${(data.failed_names || []).join(", ")}.`;
  };

  const failed = (message) => {
    live.textContent = message;
    title.textContent = "Could not run the check";
    count.textContent = "";
    rows.replaceChildren();
    const tr = document.createElement("tr");
    const td = cell(message);
    td.colSpan = 4;
    tr.append(td);
    rows.append(tr);
    panel.hidden = false;
  };

  const run = async (request, label, busy) => {
    busy.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/api/validate", request);
      const data = await res.json();
      if (!res.ok) return failed(data.error || `The server answered ${res.status}.`);
      render(data, label);
    } catch (e) {
      failed(`The check could not reach the server: ${e.message}`);
    } finally {
      busy.forEach((b) => (b.disabled = false));
    }
  };

  faults.forEach((button) => {
    button.addEventListener("click", () => {
      faults.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      const label = button.querySelector("b").textContent;
      run(
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset: button.dataset.preset }),
        },
        label,
        faults
      );
    });
  });

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = form.querySelector('input[type="file"]');
      if (!input.files.length) return failed("Choose a CSV file first.");
      faults.forEach((b) => b.setAttribute("aria-pressed", "false"));
      const body = new FormData();
      body.append("clean_data", input.files[0]);
      run({ method: "POST", body }, input.files[0].name, [form.querySelector("button")]);
    });
  }
})();
