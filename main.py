#!/usr/bin/env python3

import logging
import os
import os.path
import re
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
    parser = ArgumentParser(description="Description")
    parser.add_argument("-d", "--download-only", action="store_true")
    parser.add_argument("-e", "--email")
    parser.add_argument("-p", "--password")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-u', '--video_url')
    group.add_argument('-c', '--channel')

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
    )

    return parser.parse_args()


def get_video_title(video_id):
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()

    if response['items']:
        title = response['items'][0]['snippet']['title']
        channel_title = response['items'][0]['snippet']['channelTitle']

        return title, channel_title
    else:
        return None


def get_last_vids(channel_handle, num_vids):
    channel_handle = channel_handle.replace('@', '')
    request = youtube.channels().list(part="id", forUsername=channel_handle)
    response = request.execute()
    channel_id = response['items'][0]['id']

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
    logger.setLevel(getattr(logging, args.log_level.upper()))

    if args.video_url is not None:
        video_id = extract_video_id(args.video_url)
        if video_id is None:
            logger.error("Failed to parse video ID")
            return

        title, channel_title = get_video_title(video_id)
        videos = [title, channel_title, video_id]
    elif args.channel is not None:
        videos = get_last_vids(args.channel, 1)
    else:
        logger.error("Must specify either video URL or channel ID")
        return

    print(videos)

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
        if title is None:
            logger.warning(f"Title not found for video ID {video_id}, skipping")
            continue

        query = f"The following text is the transcript of a YouTube video titled '{title}' from the channel '{channel_title}'. Summarize the content of the video using the provided transcript:\n\n"

        transcript_path = f'./data/{video_id}.txt'
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

        send_email(
            args.email,
            args.password,
            args.email,
            args.email,
            "YouTube video summaries",
            '\n\n'.join(email_body),
            content_type='html'
        )


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
