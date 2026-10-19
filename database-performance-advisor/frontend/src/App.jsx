
import React, { useEffect, useState } from "react";
import "./index.css";

const API = "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState("Checking...");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => {
        if (!r.ok) throw new Error("API unavailable");
        return r.json();
      })
      .then(() => setHealth("Connected"))
      .catch(() => setHealth("Offline"));

    fetch(`${API}/api/stats`)
      .then((r) => {
        if (!r.ok) throw new Error("Stats unavailable");
        return r.json();
      })
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const metrics = [
    ["Customers", stats?.customers ?? "—"],
    ["Products", stats?.products ?? "—"],
    ["Orders", stats?.orders ?? "—"],
    ["Order Items", stats?.order_items ?? "—"],
  ];

  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand-icon">DB</div>
        <div>
          <h1>Database Performance Advisor</h1>
          <p>Database monitoring & optimization workspace</p>
        </div>
        <span className={`status ${health === "Connected" ? "online" : "offline"}`}>
          <span className="dot" /> API {health}
        </span>
      </header>

      <section className="hero">
        <p className="eyebrow">PERFORMANCE OVERVIEW</p>
        <h2>Your database, at a glance.</h2>
        <p>Monitor database connectivity and explore your database statistics.</p>
      </section>

      <section className="metrics">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <p>{label}</p>
            <h3>{typeof value === "number" ? value.toLocaleString() : value}</h3>
            <span>Database overview</span>
          </article>
        ))}
      </section>

      <section className="panel">
        <div>
          <h2>System status</h2>
          <p>Live connection check for your FastAPI backend.</p>
        </div>
        <span className={`status ${health === "Connected" ? "online" : "offline"}`}>
          {health}
        </span>
        {health === "Offline" && (
          <p className="hint">
            Start the backend at localhost:8000, then refresh this page.
          </p>
        )}
        {!stats && health === "Connected" && (
          <p className="hint">
            Backend is running, but statistics are unavailable. Check the /api/stats endpoint.
          </p>
        )}
      </section>

      <footer>Database Performance Advisor · Local Development</footer>
    </main>
  );
}
