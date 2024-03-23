from Memories import Memories
from youtube_transcript_api import YouTubeTranscriptApi


class YoutubeReader(Memories):
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: int = 0,
        ApiClient=None,
        user=None,
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            ApiClient=ApiClient,
            user=user,
        )

    async def write_youtube_captions_to_memory(self, video_id: str = None):
        if "?v=" in video_id:
            video_id = video_id.split("?v=")[1]
        srt = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        content = ""
        for line in srt:
            if line["text"] != "[Music]":
                content += line["text"].replace("[Music]", "") + " "
        if content != "":
            stored_content = f"From YouTube video: {video_id}\nContent: {content}"
            await self.write_text_to_memory(
                user_input=video_id,
                text=stored_content,
                external_source=f"From YouTube video: {video_id}",
            )
            return True
        return False
