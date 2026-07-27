# LS Central release/hotfix RSS feed

This turns LS Retail's official LS Central release notes and hotfix pages
into an RSS feed, refreshed automatically every 6 hours. No servers to
patch or pay for - it runs on GitHub's free Actions runners and just
commits an updated `feed.xml` back into this repo.

Built for BC4-3132: Richard Cross / Leyland SDM asked to be notified each
time an LS Central update is applied, after a field-mapping change in a
past release broke Ola's reporting.

## What it tracks

- The latest ~3 LS Central release notes (major/minor versions, e.g. 28.1, 28.0, 27.1)
- Hotfixes for the ~3 most recent versions (each category: Central, Hotels,
  Localization, Pharmacies, SCO, Shopify BC Connector, Autotests)

Source: https://help.lscentral.lsretail.com (LS Retail's own public help site).

## One-time setup (no coding needed)

1. **Create a new repository** in the business GitHub org, e.g. named
   `ls-central-release-feed`. Public is fine and recommended - the content
   is LS Retail's own published documentation, nothing confidential.
   (If it must be private, see the "Private repo" note below.)

2. **Upload these files**, keeping the folder structure exactly as-is:
   - `scrape_feed.py`
   - `requirements.txt`
   - `.github/workflows/update-feed.yml`
   - `README.md`

   Easiest way: on the repo's GitHub page, click **Add file > Upload
   files**, then drag this whole folder in. GitHub will preserve the
   `.github/workflows/update-feed.yml` path automatically.

3. **Turn on Actions** (usually on by default for a new repo): go to the
   **Actions** tab of the repo - you should see "Update LS Central RSS
   feed" listed as a workflow.

4. **Run it once manually** to generate the first feed: Actions tab >
   "Update LS Central RSS feed" > **Run workflow** button > Run workflow.
   Wait ~1-2 minutes, then refresh - you should see a new commit adding
   `feed.xml` to the repo.

5. **Get the feed URL.** Once `feed.xml` exists in the repo, its address is:

   `https://raw.githubusercontent.com/<your-org>/<repo-name>/main/feed.xml`

   Paste that into Outlook (Follow a Feed), Slack/Teams RSS connectors, or
   any RSS reader to subscribe.

After that first manual run, it updates itself every 6 hours - nothing
else to do.

## Changing how often it checks

Edit the `cron` line in `.github/workflows/update-feed.yml`. It's currently
`0 */6 * * *` (every 6 hours). `0 8 * * *` would mean once a day at 8am UTC.

## Private repo note

If the repo needs to be private, `raw.githubusercontent.com` links won't
work for RSS readers without extra auth. In that case, enable **GitHub
Pages** for the repo instead (Settings > Pages > deploy from the `main`
branch) and use `https://<org>.github.io/<repo-name>/feed.xml` - but note
standard GitHub Pages sites are themselves public, so this only helps if
the *repo* needs restricted edit access, not if the *feed content* needs
to be secret. Since this is just LS Retail's own release notes, that's
unlikely to matter.

## If scraping breaks

LS Retail could restructure their help site at any point, which would
stop the scraper from finding entries. The workflow will simply stop
updating `feed.xml` (it won't overwrite it with an empty file if nothing
was found) - check the Actions tab for a failed run, and someone will
need to adjust the parsing in `scrape_feed.py` to match the new page
layout.
