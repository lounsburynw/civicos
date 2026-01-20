# Ingest Audio

Download audio from YouTube for a jurisdiction and upload to R2 cloud storage. This bypasses YouTube bot detection by using local cookies.

## Usage

```
/ingest-audio [jurisdiction] [limit]
```

- `jurisdiction`: Target jurisdiction (default: `school-san-rafael`)
- `limit`: Max videos to process (default: 5)

## Examples

```
/ingest-audio                           # SRCS, 5 videos
/ingest-audio school-san-rafael 1       # SRCS, 1 video (test)
/ingest-audio city-san-rafael 10        # City, 10 videos
```

## Steps

1. **Check for cookies file:**

```bash
ls -la ~/Downloads/www.youtube.com_cookies.txt
```

If not found, inform user:
> Cookies file not found. Export YouTube cookies using browser extension (e.g., "Get cookies.txt LOCALLY") and save to `~/Downloads/www.youtube.com_cookies.txt`

2. **Run audio download with cookies:**

```bash
source civicos-env/bin/activate && civic-extract audio \
  --jurisdiction {jurisdiction} \
  --limit {limit} \
  --cloud \
  --cookies ~/Downloads/www.youtube.com_cookies.txt
```

3. **Report results:**

Show summary of:
- Videos processed
- Videos downloaded (new)
- Videos skipped (already in R2)
- Any failures

4. **Prompt for next steps:**

Ask user if they want to run transcription:

> Audio uploaded to R2. Run transcription now?
> ```bash
> modal run scripts/modal_ingest.py --transcripts --jurisdiction {jurisdiction} --transcripts-limit {limit}
> ```

## Why Local?

YouTube bot detection blocks downloads from cloud environments (Modal, GitHub Actions, etc.). Local download with browser cookies is the reliable workaround. The cookies authenticate the request as a logged-in user.

## Cookies Expiration

YouTube cookies typically expire after 1-2 weeks. If downloads start failing with "Sign in to confirm you're not a bot", re-export cookies from your browser.
