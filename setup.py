import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nana-bot",
    version="5.8.9.9.8.8.7.7.6.6.5.5.4.4.3.5",
    license="MIT",
    author="Vito1317",
    author_email="service@vito1317.com",
    description="A helpful Discord bot powered by Gemini",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vito1317/nana-bot",
    packages=setuptools.find_packages(exclude=["tests"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
    install_requires=[
        "pyparsing>=3.0.0",
        "urllib3>=1.26.0,<2.0",
        "discord.py",
        "google-auth>=2.14.1,<3.0.0,!=2.24.0,!=2.25.0",
        "rsa>=4.8,<5.0",
        "pyasn1>=0.4.8",
        "pyasn1-modules>=0.2.7",
        "protobuf>=3.20.2,<5.0.0",
        "google-generativeai",
        "requests",
        "beautifulsoup4",
        "discord-interactions",
        "requests",
        "aiohttp",
        "search-engine-tool-vito1317",
        "python-dotenv",
        "gtts",
        "pyttsx3",
        #"google-cloud-texttospeech",
        "google-cloud-speech",
        "torchaudio",
        "edge_tts",
        "SpeechRecognition",
        "py-cord",
        "soundfile",
        "discord-ext-voice-recv[extras]",
        "whisper",
        #"gapic-google-cloud-speech-v1",
        #"discord-ext-voice-recv @ git+https://github.com/imayhaveborkedit/discord-ext-voice-recv.git@main",
        ],
    entry_points={
        'console_scripts': [
            'nana-bot = nana_bot:main',
        ],
    },
)