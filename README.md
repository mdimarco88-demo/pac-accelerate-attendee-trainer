# PAC Accelerate Guest Trainer

This is a Streamlit training app for the upcoming Accelerate event.

It is preloaded with the attendee CSV you uploaded. The processed attendee file currently contains **341 rows** and is based on the uploaded HubSpot export.

## What it does
- Shows a face and lets users train on attendee recognition
- Works for athletes and executives
- Uses your CSV as the source list
- Tries to enrich each guest live using Wikipedia:
  - headshot
  - public summary
  - likely role / position
  - likely most-known team or organization
- Supports manual correction through override columns in the CSV

## Files
- `app.py` — main Streamlit app
- `data/accelerate_attendees.csv` — processed attendee list
- `requirements.txt` — Python dependencies

## Deploy on Streamlit Cloud
1. Create a new GitHub repo
2. Upload all files from this folder
3. In Streamlit Cloud, create a new app from that repo
4. Set the main file path to:
   `app.py`

## Manual cleanup recommended
The live enrichment is best-effort. For event-critical guests, edit `data/accelerate_attendees.csv` and fill:
- `title_override`
- `organization_override`
- `position_override`
- `image_url_override`
- `notes`

That lets you lock in exact event-facing answers for your team.
