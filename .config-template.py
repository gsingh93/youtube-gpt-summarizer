import os

youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
openai_api_key = os.environ.get("OPENAI_API_KEY", "")
smtp_password = os.environ.get("SMTP_PASSWORD", "")

# You can also use gpt-3.5-turbo-0125 which is currently 10x cheaper than gpt-4o
gpt_model = "gpt-4o"

transcript_download_dir = "./data"

# Use the special variables {title} and {channel} to insert the video title and channel
# title, respectively
user_prompt = "The following text is the transcript of a YouTube video titled '{title}' from the channel '{channel}'. Summarize the content of the video using the provided transcript, assuming the reader of the summary is well-versed in the content and is interested in the technical details. Format your response in HTML. Do not use triple backticks to create a codeblock in your response, simply output the HTML so that your entire response can be copied and pasted without needing to remove non-HTML content. Here is the transcript:\n\n"
