#!/usr/bin/env python3

import logging
import os
import os.path
import re
import shelve
import smtplib
import sys
from argparse import ArgumentParser
from email.message import EmailMessage

import tiktoken
from googleapiclient.discovery import build
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))

youtube = build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    encoding = tiktoken.encoding_for_model(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def parse_args():
    parser = ArgumentParser(
        description="Summarize YouTube videos with GPT4 and optionally email the summaries."
    )
    parser.add_argument(
        "-d",
        "--download-only",
        action="store_true",
        help="Download the transcripts and exit.",
    )
    parser.add_argument(
        "-e",
        "--email",
        help="SMTP email address for sending summarized content. This is both the sender and recipient address.",
    )
    parser.add_argument(
        "-p", "--password", help="Password for the provided SMTP email address."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-v",
        "--video",
        action="append",
        help="YouTube video URL(s) to extract transcripts and summarize.",
    )
    group.add_argument(
        "-c",
        "--channel",
        action="append",
        help="YouTube channel handle(s) to extract video transcripts from and summarize.",
    )

    parser.add_argument(
        "-n",
        "--num",
        default=1,
        help="Number of videos to summarize from the provided channel handles.",
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Set the logging level for the script.",
    )

    return parser.parse_args()


def get_video_title(video_id):
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()

    if response["items"]:
        title = response["items"][0]["snippet"]["title"]
        channel_title = response["items"][0]["snippet"]["channelTitle"]

        return title, channel_title
    else:
        return None


def get_channel_id(channel_handle):
    request = youtube.channels().list(part="id", forHandle=channel_handle)
    response = request.execute()
    if response["pageInfo"]["totalResults"] == 0:
        return None
    else:
        return response["items"][0]["id"]


def get_last_vids(channel_id, num_vids):
    request = youtube.search().list(
        part="snippet", channelId=channel_id, order="date", maxResults=num_vids
    )
    response = request.execute()

    return [
        (
            item["snippet"]["title"],
            item["snippet"]["channelTitle"],
            item["id"]["videoId"],
        )
        for item in response["items"]
    ]


def extract_video_id(youtube_url):
    pattern = r"(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(pattern, youtube_url)
    if match:
        return match.group(1)
    else:
        return None


def download_transcript(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    text = " ".join(x["text"] for x in transcript)

    return text


def main():
    args = parse_args()
    if args.num is not None and args.channel is None:
        logger.error("Must specify at least one channel handle when using -n/--num")
        return

    logger.setLevel(getattr(logging, args.log_level.upper()))

    if args.video is not None:
        videos = []
        # TODO: Allow args.video to be either an ID or a URL
        for video_url in args.video:
            video_id = extract_video_id(args.video_url)
            if video_id is None:
                logger.error("Failed to parse video ID")
                return

            title, channel_title = get_video_title(video_id)
            videos.append((title, channel_title, video_id))

            logger.info(
                f"Found video '{title}' from channel '{channel_title}' with ID {video_id}"
            )
    elif args.channel is not None:
        videos = []
        for channel_handle in args.channel:
            channel_id = get_channel_id(channel_handle)
            if channel_id is None:
                logger.error(f"Channel {channel_handle} not found")
                continue

            logger.debug(f"Channel ID for {channel_handle} is {channel_id}")

            vids = get_last_vids(channel_id, args.num)
            videos.extend(vids)
            for title, channel_title, video_id in vids:
                logger.info(
                    f"Found video '{title}' from channel '{channel_title}' with ID {video_id}"
                )
    else:
        # Should not reach here
        assert False

    # Download all transcripts
    for _, _, video_id in videos:
        transcript_path = f"./data/{video_id}.txt"
        if not os.path.exists(transcript_path):
            logger.info(f"Downloading transcript for video ID {video_id}")
            transcript = download_transcript(video_id)
            with open(transcript_path, "w") as f:
                f.write(transcript)
        else:
            logger.info(
                f"Transcript for video ID {video_id} already exists, skipping download"
            )

    if args.download_only:
        return

    email_body = []
    for title, channel_title, video_id in videos:
        with shelve.open("videos.db") as db:
            if video_id in db:
                logger.info(f"Video ID {video_id} already summarized, skipping")
                continue
            db[video_id] = (video_id, title, channel_title)

        if title is None:
            logger.warning(f"Title not found for video ID {video_id}, skipping")
            continue

        logger.info(f"Summarizing video ID {video_id}")

        query = f"The following text is the transcript of a YouTube video titled '{title}' from the channel '{channel_title}'. Summarize the content of the video using the provided transcript, assuming the reader of the summary is well-versed in the content and is interested in the technical details. Format your response in HTML. Do not use triple backticks to create a codeblock in your response, simply output the HTML so that your entire response can be copied and pasted without needing to remove non-HTML content. Here is the transcript:\n\n"

        transcript_path = f"./data/{video_id}.txt"
        with open(transcript_path) as f:
            query += f.read()

        logger.info(
            "Sending query with {0} tokens".format(
                num_tokens_from_string(query, "gpt-4-turbo")
            )
        )
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a summarization assistant, able to take long pieces of text and summarize them for users.",
                },
                {"role": "user", "content": query},
            ],
            model="gpt-4-turbo",
        )
        print(chat_completion)

        content = chat_completion.choices[0].message.content

        email_body.append(f"<h2>Summary for video '{title}':</h2>\n\n{content}")
        logger.debug(f"Summary for video '{title}':\n\n{content}\n\n")

    if args.email is not None:
        if args.password is None:
            logger.error("Email password not provided")
            return

        if len(email_body) > 0:
            send_email(
                args.email,
                args.password,
                args.email,
                args.email,
                "YouTube video summaries",
                "\n\n".join(email_body),
                content_type="html",
            )
            logger.info("Email sent")
        else:
            logger.info("No new videos to summarize, not sending email")


def send_email(
    smtp_user,
    smtp_password,
    from_email,
    to_email,
    subject,
    content,
    content_type="plain",
    smtp_server="smtp.gmail.com",
    port=587,
):
    email = EmailMessage()
    email["From"] = from_email
    email["To"] = to_email
    email["Subject"] = subject

    if content_type == "html":
        email.set_content("HTML support required to see email")
        email.add_alternative(content, subtype="html")
    else:
        email.set_content(content)

    server = smtplib.SMTP(smtp_server, port)
    server.starttls()

    server.login(smtp_user, smtp_password)

    server.send_message(email)

    server.quit()


if __name__ == "__main__":
    main()
