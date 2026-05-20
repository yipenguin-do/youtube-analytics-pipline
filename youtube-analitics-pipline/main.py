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

def get_latest_video_id(youtube, channel_id):
    ch = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()

    items = ch.get("items", [])
    if not items:
        return None

    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    pl = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads,
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

    # -------------------------
    # Step1:
    # 最新video_id収集
    # -------------------------

    for cid in channel_ids:

        state_manager.init_channel(cid)

        video_id = get_latest_video_id(youtube, cid)

        if not video_id:
            continue

        # 先に保存
        state_manager.state[cid]["video_id"] = video_id

    # -------------------------
    # Step2:
    # 一括ライブ判定
    # -------------------------

    results = check_video(
        youtube,
        state_manager
    )

    # -------------------------
    # Step3:
    # state更新
    # -------------------------

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