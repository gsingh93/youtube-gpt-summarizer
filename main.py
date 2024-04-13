#!/usr/bin/env python3

import tiktoken
from openai import OpenAI


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    encoding = tiktoken.encoding_for_model(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


import os
import os.path
import re
import smtplib
import sys
from argparse import ArgumentParser
from email.message import EmailMessage

from googleapiclient.discovery import build
# from llama_index.core import (
#     Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex,
#     load_index_from_storage
# )
# from llama_index.core.embeddings import resolve_embed_model
# from llama_index.llms.ollama import Ollama
# from llama_index.llms.openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

youtube = None
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def parse_args():
    parser = ArgumentParser(description='Description')
    parser.add_argument('-d', '--download-only', action='store_true')
    parser.add_argument('-e', '--email')
    parser.add_argument('-p', '--password')

    # TODO: Make these mutually exclusive
    parser.add_argument('video_url', nargs='?')
    parser.add_argument(
        '-c',
        '--channel_id',
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
        return None  # Video ID not found or private video


def get_last_vids(channel_id, num_vids):
    # TODO: Allow the user to pass in a channel name instead
    # TODO: don't hardcode the channel name
    request = youtube.channels().list(
        part="id",
        forUsername="BlackHatOfficialYT"  # Use the username here, without '@'
    )
    response = request.execute()
    channel_id = response['items'][0]['id']

    request = youtube.search().list(
        part="snippet", channelId=channel_id, order="date", maxResults=num_vids
    )
    response = request.execute()

    return [
        (
            item['snippet']['title'], item['snippet']['channelTitle'],
            item['id']['videoId']
        ) for item in response['items']
    ]


def extract_video_id(youtube_url):
    pattern = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, youtube_url)
    if match:
        return match.group(1)
    else:
        return None


def download_transcript(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    text = ' '.join(x['text'] for x in transcript)

    return text


# local = False
# if local:
#     Settings.embed_model = resolve_embed_model("local:BAAI/bge-small-en-v1.5")
#     Settings.llm = Ollama(model="mistral", request_timeout=30.0)
# else:
#     Settings.llm = OpenAI(temperature=0, model="gpt-4")


def main():
    args = parse_args()

    if args.video_url is not None:
        video_id = extract_video_id(args.video_url)
        if video_id is None:
            print("Failed to parse video ID")
            return

        title, channel_title = get_video_title(video_id)
        videos = [title, channel_title, video_id]
    elif args.channel_id is not None:
        videos = get_last_vids(args.channel_id, 3)
    else:
        print("Must specify either video URL or channel ID")
        return

    print(videos)

    # Download all transcripts
    for _, _, video_id in videos:
        transcript_path = f'./data/{video_id}.txt'
        if not os.path.exists(transcript_path):
            print(f"Downloading transcript for video ID {video_id}")
            transcript = download_transcript(video_id)
            with open(transcript_path, 'w') as f:
                # f.write(
                #     f"The following text is the transcript from the YouTube video with ID {video_id}"
                # )
                # if title is not None:
                #     f.write(f" and title '{title}'")
                # f.write("\n\n")
                f.write(transcript)

    # # TODO: we're constantly adding files, how do we only add the new ones?
    # if not os.path.exists(PERSIST_DIR):
    #     documents = SimpleDirectoryReader("data").load_data()
    #     index = VectorStoreIndex.from_documents(documents)
    #     index.storage_context.persist(persist_dir=PERSIST_DIR)
    # else:
    #     storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    #     index = load_index_from_storage(storage_context)

    if args.download_only:
        return

    # index = VectorStoreIndex()
    # query_engine = index.as_query_engine()

    email_body = []
    for title, channel_title, video_id in videos:
        if title is None:
            print(f"Warning: title not found for video ID {video_id}, skipping")
            continue

        query = f"The following text is the transcript of a YouTube video titled '{title}' from the channel '{channel_title}'. Summarize the content of the video using the provided transcript:\n\n"

        transcript_path = f'./data/{video_id}.txt'
        with open(transcript_path) as f:
            query += f.read()

        print(
            "Sending query with {0} tokens".format(
                num_tokens_from_string(query, 'gpt-4-turbo')
            )
        )
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role":
                        "system",
                    "content":
                        "You are a summarization assistant, able to take long pieces of text and summarize them for users."
                }, {
                    "role": "user",
                    "content": query
                }
            ],
            model="gpt-4-turbo",
        )
        print(chat_completion)

        content = chat_completion.choices[0].message.content

        email_body.append(f"Summary for video '{title}':\n\n{content}")
        print(f"Summary for video '{title}':\n\n{content}\n\n")

    if args.email is not None:
        if args.password is None:
            print("Email password not provided")
            return

        send_email(
            args.email, args.password, args.email, args.email,
            "YouTube video summaries", '\n\n'.join(email_body)
        )


def send_email(
    smtp_user,
    smtp_password,
    from_email,
    to_email,
    subject,
    content,
    smtp_server='smtp.gmail.com',
    port=587
):
    email = EmailMessage()
    email['From'] = from_email
    email['To'] = to_email
    email['Subject'] = subject
    email.set_content(content)

    server = smtplib.SMTP(smtp_server, port)
    server.starttls()

    server.login(smtp_user, smtp_password)

    server.send_message(email)

    server.quit()


if __name__ == '__main__':
    youtube = build('youtube', 'v3', developerKey=os.environ['YOUTUBE_API_KEY'])
    main()
