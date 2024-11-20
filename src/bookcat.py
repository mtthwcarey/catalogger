import os
import sys
import openai
import csv
import speech_recognition as sr
import requests
import time
import logging
from datetime import datetime

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Paths to input/output and log files
DATA_DIR = "data"
LOGS_DIR = "logs"
INPUT_FILE = os.path.join(DATA_DIR, "input.txt")
OUTPUT_FILE = os.path.join(DATA_DIR, "book_catalog.csv")
LOG_FILE = os.path.join(LOGS_DIR, "batch_test.log")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Set up logging configuration
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# Suppress ALSA verbosity
class SuppressAlsaWarnings:
    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self._original_stderr

def recognize_speech():
    """Capture speech from the microphone and convert it to text."""
    recognizer = sr.Recognizer()
    try:
        with SuppressAlsaWarnings():
            with sr.Microphone() as source:
                print("Adjusting for ambient noise... Please wait.")
                recognizer.adjust_for_ambient_noise(source)
                print("You can speak now.")
                audio = recognizer.listen(source)
                print("Audio captured. Processing...")
        # Recognize speech
        text = recognizer.recognize_google(audio)
        logging.info(f"Recognized speech: {text}")
        print(f"Recognized speech: {text}")
        return text
    except sr.UnknownValueError:
        logging.warning("Speech was not understood. Please try again.")
        print("Speech was not understood. Please try again.")
        return None
    except sr.RequestError as e:
        logging.error(f"Error with the Google Speech Recognition API: {e}")
        print(f"Error with the Google Speech Recognition API: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during speech recognition: {e}")
        print(f"Unexpected error: {e}")
        return None

def parse_book_details(description):
    """Extract book details using OpenAI's ChatCompletion API."""
    prompt = f"""
    Extract the following details from this book description: 
    - Title
    - Author
    - Format (e.g., hardcover, paperback)
    - Year

    Description: {description}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that extracts book details from text."},
                {"role": "user", "content": prompt}
            ]
        )
        details = response['choices'][0]['message']['content'].strip()
        logging.info(f"Book details extracted: {details}")
        return details
    except Exception as e:
        logging.error(f"Error with OpenAI API: {e}")
        print(f"Error with OpenAI API: {e}")
        return None

def fetch_metadata(title, author):
    """Fetch additional metadata from Google Books API."""
    api_url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"intitle:{title}+inauthor:{author}",
        "maxResults": 1
    }

    try:
        logging.info(f"Fetching metadata for Title: '{title}', Author: '{author}'")
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        time.sleep(1)  # Add a 1-second delay to avoid hitting API rate limits
        data = response.json()

        if "items" in data:
            book = data["items"][0]["volumeInfo"]
            metadata = {
                "Title": book.get("title", "Unknown"),
                "Author": ", ".join(book.get("authors", ["Unknown"])),
                "Publisher": book.get("publisher", "Unknown"),
                "PublishedDate": book.get("publishedDate", "Unknown"),
                "ISBN": next((id["identifier"] for id in book.get("industryIdentifiers", []) if id["type"] == "ISBN_13"), "Unknown"),
                "PageCount": book.get("pageCount", "Unknown"),
                "Categories": ", ".join(book.get("categories", ["Unknown"])),
                "Description": book.get("description", "No description available"),
                "CoverURL": book.get("imageLinks", {}).get("thumbnail", "No cover available")
            }
            logging.info(f"Metadata successfully fetched: {metadata}")
            return metadata
        else:
            logging.info(f"No metadata found for Title: '{title}', Author: '{author}'")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching metadata for Title: '{title}', Author: '{author}': {e}")
        return None

def save_to_csv(book_details, filename=OUTPUT_FILE):
    """Save book details to a CSV file, updating headers if needed."""
    try:
        existing_data = []
        existing_headers = set()
        file_exists = os.path.isfile(filename)

        if file_exists:
            with open(filename, "r", newline="") as f:
                reader = csv.DictReader(f)
                existing_data = list(reader)
                existing_headers = set(reader.fieldnames or [])

        # Ensure "Index Number" retains its three-digit formatting
        if "Index Number" in book_details:
            book_details["Index Number"] = str(book_details["Index Number"]).zfill(3)

        new_headers = existing_headers.union(book_details.keys())
        sorted_headers = sorted(new_headers)

        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sorted_headers)
            writer.writeheader()
            for row in existing_data:
                complete_row = {header: row.get(header, "") for header in sorted_headers}
                writer.writerow(complete_row)
            complete_book_details = {header: book_details.get(header, "") for header in sorted_headers}
            writer.writerow(complete_book_details)

        print(f"Book details saved to {filename}")
    except Exception as e:
        logging.error(f"Error saving to CSV: {e}")
        print(f"Error saving to CSV: {e}")

def process_batch_file(filename):
    """Process a text file containing multiple book descriptions."""
    notes_file = os.path.join(DATA_DIR, "entry_notes.txt")  # Updated file name

    try:
        with open(filename, "r") as f:
            # Split lines and filter out empty ones
            descriptions = [line.strip() for line in f.readlines() if line.strip()]
        logging.info(f"Found {len(descriptions)} descriptions in {filename}.")
        print(f"Found {len(descriptions)} descriptions in {filename}.")

        # Clear or create the notes file
        with open(notes_file, "w") as nf:
            nf.write("Entry Notes Log\n")
            nf.write("=" * 20 + "\n")

        for idx, description in enumerate(descriptions, start=1):
            logging.debug(f"Starting processing for book {idx}.")
            print(f"\nProcessing book {idx}/{len(descriptions)}...")
            logging.info(f"Processing book {idx}: {description[:50]}...")  # Log preview of description

            # Extract book details
            entry_note = "No problems"  # Default note for successful entries
            try:
                book_details_text = parse_book_details(description)
                if not book_details_text:
                    entry_note = f"Skipped '{description}' - could not extract book details."
                    with open(notes_file, "a") as nf:
                        nf.write(entry_note + "\n")
                    print(entry_note)
                    logging.warning(f"Book {idx}: Failed to extract book details.")
                    continue
            except Exception as e:
                entry_note = f"Skipped '{description}' - error extracting book details: {e}."
                with open(notes_file, "a") as nf:
                    nf.write(entry_note + "\n")
                print(entry_note)
                logging.error(f"Book {idx}: Extraction failed with error: {e}")
                continue

            # Parse extracted details
            book_details = {}
            for line in book_details_text.split("\n"):
                try:
                    key, value = line.split(":", 1)
                    book_details[key.strip().lstrip("-").strip()] = value.strip()
                except ValueError:
                    logging.warning(f"Book {idx}: Malformed line in details: {line}")
                    continue

            # Fetch metadata
            metadata_found = False
            try:
                metadata = fetch_metadata(book_details.get("Title", ""), book_details.get("Author", ""))
                if metadata:
                    book_details.update(metadata)
                    metadata_found = True
                    print(f"Metadata found and added for book {idx}.")
                    logging.info(f"Book {idx}: Metadata fetched successfully.")
            except Exception as e:
                logging.error(f"Book {idx}: Metadata fetch failed with error: {e}")

            # Check if book_details has meaningful data
            if not any(value.strip() for value in book_details.values()):
                # If all fields are empty, treat as skipped
                entry_note = f"Skipped '{description}' - insufficient data to save."
                with open(notes_file, "a") as nf:
                    nf.write(entry_note + "\n")
                print(entry_note)
                logging.warning(f"Book {idx}: Insufficient data to save.")
                continue

            # Add Index Number and Entry Time
            book_details["Index Number"] = f"{idx:03}"  # Correctly padded index number
            book_details["Entry Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not metadata_found:
                entry_note = f"Added '{description}' to CSV without metadata."

            # Save to CSV and log the note
            try:
                book_details["Entry Notes"] = entry_note  # Ensure entry_note reflects the actual status
                save_to_csv(book_details)
                if not metadata_found:
                    with open(notes_file, "a") as nf:
                        nf.write(entry_note + "\n")
                    print(entry_note)
                    logging.info(f"Book {idx}: Added to CSV without metadata.")
                else:
                    print(f"Book {idx} saved successfully!")
                    logging.info(f"Book {idx}: Processed successfully.")
            except Exception as e:
                entry_note = f"Skipped '{description}' - error saving to CSV: {e}."
                with open(notes_file, "a") as nf:
                    nf.write(entry_note + "\n")
                print(entry_note)
                logging.error(f"Book {idx}: Failed to save with error: {e}")

        print("Batch processing complete.")
        logging.info("Batch processing completed successfully.")

    except FileNotFoundError:
        print(f"File not found: {filename}")
        logging.error(f"Batch file {filename} not found.")
    except Exception as e:
        print(f"An error occurred while processing the batch file: {e}")
        logging.error(f"Batch processing failed: {e}")

def main():
    print("Starting the book cataloging tool...")

    while True:
        print("\nHow would you like to input a book?")
        print("1. Speak description")
        print("2. Type description")
        print("3. Process batch file")
        print("4. Exit")
        choice = input("Choose an option (1/2/3/4): ").strip()

        if choice == "4":
            print("Exiting the book cataloging tool. Goodbye!")
            break

        if choice == "1":
            description = recognize_speech()
            if not description:
                print("No input captured. Returning to menu.")
                continue
        elif choice == "2":
            description = input("Enter the book description: ").strip()
        elif choice == "3":
            filename = input("Enter the path to the batch file: ").strip()
            process_batch_file(filename)
            continue

        print("Extracting book details...")
        book_details_text = parse_book_details(description)
        if not book_details_text:
            print("Could not extract book details.")
            continue

        book_details = {}
        for line in book_details_text.split("\n"):
            try:
                key, value = line.split(":", 1)
                book_details[key.strip().lstrip("-").strip()] = value.strip()
            except ValueError:
                continue

        metadata = fetch_metadata(book_details.get("Title", ""), book_details.get("Author", ""))
        if metadata:
            book_details.update(metadata)

        save_to_csv(book_details)
        print("Book added successfully!")

if __name__ == "__main__":
    main()

