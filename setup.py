import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nana-bot",
    version="5.8.9.9.4",
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
        "discord.py",
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
        "google-cloud-texttospeech",
        "torchaudio",
        "edge_tts",
        "SpeechRecognition",
        "py-cord",
        "soundfile",
        "discord-ext-voice-recv[extras]",
        #"discord-ext-voice-recv @ git+https://github.com/imayhaveborkedit/discord-ext-voice-recv.git@main",
        "discord.py[voice]==2.5.2"
        ],
    entry_points={
        'console_scripts': [
            'nana-bot = nana_bot:main',
        ],
    },
)