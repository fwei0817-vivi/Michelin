import { useState } from "react";
import { loadStoredProfiles, persistProfile, profileHistory } from "../api";
import type { DinerProfile, ProfileSnapshot } from "../types";

export function ProfileHistory({diners, onLoad}: {diners: DinerProfile[]; onLoad: (people: DinerProfile[]) => void}) {
  const [scope, setScope] = useState("synthetic-demo");
  const [selected, setSelected] = useState("");
  const [revisions, setRevisions] = useState<Record<string, number>>({});
  const [history, setHistory] = useState<ProfileSnapshot[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const person = diners.find(p => p.id === selected) ?? diners[0];
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(""); setStatus("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  return <details className="sheet p-4 my-4">
    <summary>Local synthetic profile history</summary>
    <p className="helper">Explicit saves only. Scope is a caller-provided namespace, not an account or access control. Use synthetic people. History survives local restarts while the SQLite file remains; cloud workspace reset may erase it.</p>
    <label className="field-label">Profile scope<input className="field" value={scope} disabled={busy} onChange={e => {setScope(e.target.value); setRevisions({}); setHistory([]); setStatus(""); setError("");}}/></label>
    <button className="btn btn-outline btn-small my-2" disabled={busy || !scope} onClick={() => void run(async () => {
      const people = await loadStoredProfiles(scope);
      if (!people.length) { setStatus("No saved profiles in this scope. Save a synthetic person first."); return; }
      const snapshots = await Promise.all(people.map(p => profileHistory(scope, p.id)));
      setRevisions(Object.fromEntries(snapshots.map(rows => [rows.at(-1)!.profile.id, rows.at(-1)!.revision])));
      setHistory([]); onLoad(people); setStatus(`Loaded ${people.length} saved synthetic profiles.`);
    })}>Load saved group</button>
    {!!person && <>
      <label className="field-label">Person to save or inspect<select className="field" value={person.id} disabled={busy} onChange={e => {setSelected(e.target.value); setHistory([]);}}>
        {diners.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
      </select></label>
      <div className="flex flex-wrap gap-2 my-2">
        <button className="btn btn-outline btn-small" disabled={busy || !scope} onClick={() => void run(async () => {
          const saved = await persistProfile(scope, person, revisions[person.id] ?? 0);
          setRevisions(prev => ({...prev, [person.id]: saved.revision}));
          setHistory(await profileHistory(scope, person.id)); setStatus(`Saved ${person.name}, revision ${saved.revision}.`);
        })}>Save current person</button>
        <button className="btn btn-outline btn-small" disabled={busy || !scope} onClick={() => void run(async () => {
          const rows = await profileHistory(scope, person.id); setHistory(rows);
          setRevisions(prev => ({...prev, [person.id]: rows.at(-1)!.revision}));
          setStatus(`History: ${rows.length} revisions. Current table is unchanged.`);
        })}>View history</button>
      </div>
    </>}
    {status && <p role="status">{status}</p>}
    {error && <p role="alert">{error} For a revision conflict, load the saved group before editing again.</p>}
    {history.length > 0 && <ol aria-label="Profile revisions">{history.map(row => <li key={row.revision} className="my-2">
      <strong>Revision {row.revision}</strong> · {row.created_at}<br/>
      Likes: {row.profile.likes.join(", ") || "none recorded"}; dislikes: {row.profile.dislikes.join(", ") || "none recorded"}.<br/>
      Restrictions: {[...row.profile.allergies, ...row.profile.diets].join(", ") || "none recorded"}.
    </li>)}</ol>}
  </details>;
}
