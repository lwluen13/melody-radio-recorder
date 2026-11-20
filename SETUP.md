# Melody FM recorder on GitHub (no PC needed)

Every weekday this records Melody FM from 10:00 to 11:00 Singapore time, turns it into text, and saves
`YYYY-MM-DD.txt` in your Google Drive `RadioScreener` folder. Your Claude task at 11:30 then reads it as before.

Nothing private goes into GitHub. The repository is public, so it only holds the code. The link and the
password for Google Drive are kept as GitHub "secrets" (hidden, encrypted).

Do not share the secret or the Apps Script link with anyone, including in chat.

## Step 1: Put the files on GitHub

1. On github.com, click the + at the top right, then "New repository".
2. Name: `melody-radio-recorder`. Choose **Public**. Do not tick "Add a README". Click "Create repository".
3. On the new page, click "uploading an existing file".
4. Drag everything from this folder into the page: `cloud_record.py`, `config.json`, `requirements.txt`,
   `heartbeat.txt`, `Code.gs`, `SETUP.md` and the `.github` folder.
   If the `.github` folder does not upload, click "Add file", then "Create new file". Type
   `.github/workflows/record.yml` as the name (typing the slashes makes the folders), paste the text from
   the `record.yml` file, then click "Commit changes".
5. Click "Commit changes".

## Step 2: Make the Google Drive receiver (Apps Script)

1. Open your `RadioScreener` folder in Google Drive. The web address ends with `/folders/` and a long text.
   Copy that long text. This is the folder ID.
2. Go to script.google.com and click "New project".
3. Delete the sample code. Paste everything from `Code.gs`.
4. Replace `PASTE_FOLDER_ID_HERE` with your folder ID.
5. Replace `PASTE_YOUR_LONG_RANDOM_SECRET_HERE` with a long random text you make up (30 or more letters and
   numbers). Keep it somewhere safe for Step 3.
6. Click Deploy, then "New deployment". Click the gear icon and choose "Web app".
   Set "Execute as" to **Me** and "Who has access" to **Anyone**. Click Deploy.
7. Google will ask you to authorize. Click "Authorize access", choose your account, then "Advanced", then
   "Go to (project name) (unsafe)", then "Allow". This is normal for your own script.
8. Copy the "Web app URL" shown at the end.

## Step 3: Give GitHub the link and the secret

1. In your GitHub repository, click Settings, then "Secrets and variables", then "Actions".
2. Click "New repository secret". Name: `APPS_SCRIPT_URL`. Value: the Web app URL. Save.
3. Click "New repository secret" again. Name: `APPS_SCRIPT_SECRET`. Value: the secret from Step 2. Save.

## Step 4: Test it

1. Click the "Actions" tab. If asked, click the green button to enable workflows.
2. Click "Record and transcribe Melody FM" on the left, then "Run workflow".
3. Leave `test_minutes` as 2 and click the green "Run workflow" button.
4. Wait about 5 to 10 minutes (the first run downloads the speech model). Refresh the page.
5. A green tick means it worked. Check your `RadioScreener` folder for `test-cloud-YYYY-MM-DD.txt`.
6. A red cross means it failed. Open the run, click the step with the red cross, and send me the last 20 lines
   of the log. The log does not show the secret or the transcript.

The most important thing this test shows is whether Melody FM allows GitHub's computers to listen to the
stream. If it fails with "No audio was recorded", the stream is blocked from there and this free route will not work.

## Step 5: A longer test (to measure the time)

Run the workflow again with `test_minutes` set to 10. Note how long the "Record, transcribe and upload"
step takes. Transcribing one hour should take less than the free job limit (the job stops after 4 hours).

## Step 6: Switch over

1. The schedule is already on. It starts at 9:40 Singapore time and waits until 10:00 to begin recording.
2. After the first full day works (a real `YYYY-MM-DD.txt` appears with correct text), switch off the old
   PC task: open Task Scheduler on your PC, right-click `RadioScreener`, and click "Disable".
   If both run, they save a file with the same name and one will overwrite the other.
3. Your Claude scheduled task and the Google Sheet do not change.

## Things to know

- GitHub can start scheduled jobs a few minutes late. That is fine, because this one starts at 9:40.
- GitHub switches off scheduled jobs after 60 days with no activity in the repository. The job adds a small
  `heartbeat.txt` commit each day to prevent this. If the schedule ever stops, open the Actions tab and
  click the button to enable it again.
- Transcript times are offsets from 10:00 Singapore time, the same as before. Duplicate audio is skipped,
  so the transcript should no longer run past one hour.
- To change keywords, the speech model or the language, edit `config.json` in the repository.
