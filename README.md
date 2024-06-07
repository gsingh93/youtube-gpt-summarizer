# YouTube GPT Summarizer

A Python script to summarize individual YouTube videos or the latest videos on YouTube channels and optionally send you an email with the summaries.

Currently only Gmail accounts are supported when sending email.

## Installation

```bash
# Clone project
git clone https://github.com/gsingh93/youtube-gpt-summarizer
cd youtube-gpt-summarizer

# Install poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Or if you have pipx already installed: pipx install poetry

# Install dependencies
poetry install

# Activate venv
source .venv/bin/activate

# Display help
./main.py -h
```

## Configuration

Copy the template configuration to `config.py`:
```
cp .config-template.py config.py
```

You must create your own [OpenAI API key](https://platform.openai.com/api-keys) and [YouTube API key](https://developers.google.com/youtube/registering_an_application). You can optionally create a [Gmail app password](https://support.google.com/mail/answer/185833?hl=en) if you want to get summary emails.

Set the values of `youtube_api_key`, `openai_api_key` and `smtp_password` to the keys you created above. Alternatively, if you set the `YOUTUBE_API_KEY`, `OPENAI_API_KEY`, and `SMTP_PASSWORD` environment variables, they will automatically be loaded by the default `config.py`.

You can optionally change `gpt-4o` to `gpt-3.5-turbo-0125` which is 10 times cheaper than GPT 4o, but not as powerful.

The default `user_prompt` is configured so that the output is formatted in HTML, which makes for nicer emails. Feel free to customize this however you want. The `{title}` and `{channel}` strings in the text will be replaced by the video title and channel.

## Usage

```
usage: main.py [-h] [-d] [-e EMAIL] (-v VIDEO | -c CHANNEL) [-n NUM]
               [--log-level {debug,info,warning,error,critical}]

Summarize YouTube videos with GPT4 and optionally email the summaries.

options:
  -h, --help            show this help message and exit
  -d, --download-only   Download the transcripts and exit.
  -e EMAIL, --email EMAIL
                        SMTP email address for sending summarized content. This is both the sender and recipient
                        address.
  -v VIDEO, --video VIDEO
                        YouTube video URL(s) to extract transcripts and summarize.
  -c CHANNEL, --channel CHANNEL
                        YouTube channel handle(s) to extract video transcripts from and summarize.
  -n NUM, --num NUM     Number of videos to summarize from the provided channel handles.
  --log-level {debug,info,warning,error,critical}
                        Set the logging level for the script.
```

For example, to send an email to user@example.com with the summary of the latest two videos on the [Veritasium](https://www.youtube.com/channel/UCHnyfMqiRRG1u-2MsSQLbXA) channel:
```
./main.py -c veritasium -n 2 -e user@example.com
```

Note that video summarization requires that the video have a transcript. This is present for most videos, but not all.
