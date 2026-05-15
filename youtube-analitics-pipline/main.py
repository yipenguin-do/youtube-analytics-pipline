from googleapiclient.discovery import build
from google.cloud import bigquery
from dotenv import load_dotenv
from datetime import datetime
import time
import pandas as pd
import os

load_dotenv()

API_KEY = os.getenv("YOUTUBE_DATA_API_KEY")

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

request = youtube.search().list(
    part="snippet",
    channelId="UC1DCedRgGHBdm81E1llLhOQ",  
    maxResults=5,
    order="date",
    eventType="live"
)

response = request.execute()

rows = []

for item in response["items"]:
    rows.append({
    "video_id": item["id"]["videoId"],
    "title": item["snippet"]["title"],
    "description": item["snippet"]["description"],
    "published_at": item["snippet"]["publishedAt"],
    "ingested_at": datetime.utcnow()
})

df = pd.DataFrame(rows)
print(df)

table_id = "your_project.dataset.videos_raw"

schema = [
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("description", "STRING"),
    bigquery.SchemaField("published_at", "TIMESTAMP"),
]