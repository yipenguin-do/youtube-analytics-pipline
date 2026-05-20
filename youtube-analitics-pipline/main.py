from googleapiclient.discovery import build
from dotenv import load_dotenv
from datetime import datetime, timezone

import feedparser
import pandas as pd
import json
import os


STATE_FILE = "state.json"


class StateManager:
    def __init__(self, path=STATE_FILE):
        self.path = path
        self.state = self.load()

    def load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r") as f:
            return json.load(f)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=2)

    def init_channel(self, channel_id):
        if channel_id not in self.state:
            self.state[channel_id] = {
                "video_id": None,
                "status": "idle",
                "started_at": None,
                "viewer_count": None,
                "last_checked": None
            }
            self.save()

    def update_channel(self, channel_id, data):
        self.state[channel_id] = data
        self.save()

    def update_last_checked(self, channel_id):
        now = datetime.now(timezone.utc).isoformat()
        self.state[channel_id]["last_checked"] = now
        self.save()



def get_latest_video_id_rss(channel_id):
    
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    feed = feedparser.parse(url)

    if not feed.entries[0]:
        return None
    
    entry = feed.entries[0]

    return entry.yt_videoid


# =========================
# Step 2: ライブ判定
# =========================

def check_video(youtube, state_manager):

    video_ids = []

    for cid, data in state_manager.state.items():

        video_id = data.get("video_id")

        if video_id:
            video_ids.append(video_id)

    if not video_ids:
        return {}

    v = youtube.videos().list(
        part="snippet,liveStreamingDetails",
        id=",".join(video_ids)
    ).execute()

    results = {}

    for item in v.get("items", []):

        vid = item["id"]

        live = item.get("liveStreamingDetails", {})
        snippet = item.get("snippet", {})

        live_broadcast_content = snippet.get(
            "liveBroadcastContent"
        )

        concurrent = live.get(
            "concurrentViewers"
        )

        is_live = (
            live_broadcast_content == "live"
            or concurrent is not None
        )

        results[vid] = {
            "is_live": is_live,
            "started_at": live.get(
                "actualStartTime"
            ),
            "viewer_count": concurrent
        }

    return results


# =========================
# Step 3: メイン処理
# =========================

def run(youtube, state_manager, channel_ids):

    # ① RSSで最新video_id取得（playlistItems削除）
    for cid in channel_ids:

        state_manager.init_channel(cid)

        video_id = get_latest_video_id_rss(cid)

        if not video_id:
            continue

        # 既存state更新（video_id差し替え）
        state_manager.state[cid]["video_id"] = video_id

    # ② ライブ判定（既存）
    results = check_video(youtube, state_manager)

    # ③ state更新
    for cid, data in state_manager.state.items():

        video_id = data.get("video_id")

        if not video_id:
            continue

        result = results.get(video_id)

        if result and result["is_live"]:

            state_manager.update_channel(cid, {
                "video_id": video_id,
                "status": "live",
                "started_at": result["started_at"],
                "viewer_count": result["viewer_count"],
                "last_checked": datetime.now(timezone.utc).isoformat()
            })

        else:

            state_manager.update_channel(cid, {
                "video_id": video_id,
                "status": "idle",
                "started_at": None,
                "viewer_count": None,
                "last_checked": datetime.now(timezone.utc).isoformat()
            })

        print(cid, "->", state_manager.state[cid])

# =========================
# bootstrap
# =========================

def main():
    load_dotenv()
    api_key = os.getenv("YOUTUBE_DATA_API_KEY")

    youtube = build("youtube", "v3", developerKey=api_key)

    df = pd.read_csv("hololive_channel_15.csv")
    df["channel_id"] = df["url"].str.replace(
        "https://www.youtube.com/channel/",
        "",
        regex=False
    )

    channel_ids = df["channel_id"].tolist()

    state_manager = StateManager()

    run(youtube, state_manager, channel_ids)


if __name__ == "__main__":
    main()