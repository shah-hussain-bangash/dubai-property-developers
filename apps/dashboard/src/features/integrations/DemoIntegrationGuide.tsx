export function DemoIntegrationGuide() {
  return <section className="panel" aria-labelledby="demo-integration-guide-title">
    <div className="panel-header"><h2 className="panel-title" id="demo-integration-guide-title">What these integration statuses mean</h2></div>
    <p>This is a static demo catalog, not a connection or credential check. Status labels below do not inspect the running services or confirm a live connection.</p>
    <dl>
      <div><dt>Mock</dt><dd>Simulated behavior for fictional workflows. A successful mock run does not prove a live provider works.</dd></div>
      <div><dt>Not configured</dt><dd>The demo lists this service as awaiting setup. This page does not read or validate your saved configuration.</dd></div>
      <div><dt>Pending access</dt><dd>Authorized provider access is still required. This demo does not scrape listing portals.</dd></div>
    </dl>
    <p>Google Workspace email and calendar access is separate from Google sign-in. These demo links do not activate either feature.</p>
    <p>To try the mock behavior, use <a href="/workflows#demo-scenario-title">Run a guided demo</a> or <a href="/conversations#demo-reply-title">Prepare an unsent demo reply</a>. Both use fictional data; nothing is sent or booked.</p>
  </section>;
}
