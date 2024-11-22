from setuptools import setup, find_packages

setup(
    name="Catalogger",
    version="0.1.0",  
    description="To more easily catalog a book collection.", 
    long_description=open("README.md").read(), 
    long_description_content_type="text/markdown",
    author="Matthew Carey",
    author_email="mtthwcarey@gmail.com",
    url="https://github.com/mtthwcarey/catalogger",
    packages=find_packages(),  
    include_package_data=True, 
    install_requires=[
        "openai==0.27.8", 
        "requests==2.32.3",
        "SpeechRecognition", 
        "pyaudio",  
    ],
    classifiers=[
        "Intended Audience :: Other Audience :: Libraries",
        "Intended Audience :: Education",
        "Topic :: Office/Business :: Library Management",
        "Topic :: Utilities :: Information Management",
        "Topic :: Multimedia :: Sound/Audio :: Analysis",
        "Topic :: Multimedia :: Sound/Audio :: Speech Recognition",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    keywords="books, library, inventory, cataloging, collections",
    python_requires=">=3.6", 
    license="MIT",
)

