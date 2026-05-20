from googleapiclient.discovery import build
from dotenv import load_dotenv
from datetime import datetime, timezone
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


# =========================
# Step 1: 最新動画取得
# =========================

def get_uploads_map(youtube, channel_ids):

    res = youtube.channels().list(
        part="contentDetails",
        id=",".join(channel_ids)
    ).execute()

    uploads_map = {}

    for item in res.get("items", []):

        cid = item["id"]

        uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]

        uploads_map[cid] = uploads

    return uploads_map


def get_latest_video_id(youtube, uploads_playlist_id):

    pl = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=1
    ).execute()

    items = pl.get("items", [])

    if not items:
        return None

    return items[0]["snippet"]["resourceId"]["videoId"]

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

    # ① 全チャンネルのuploadsを1回で取得
    uploads_map = get_uploads_map(youtube, channel_ids)

    # ② 最新video_id取得（playlistItemsはそのまま）
    for cid in channel_ids:

        state_manager.init_channel(cid)

        uploads = uploads_map.get(cid)

        if not uploads:
            continue

        video_id = get_latest_video_id(youtube, uploads)

        if not video_id:
            continue

        state_manager.state[cid]["video_id"] = video_id

    # ③ ライブ判定（既存）
    results = check_video(youtube, state_manager)

    # ④ state更新（変更なし）
    for cid, data in state_manager.state.items():

        video_id = data.get("video_id")

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