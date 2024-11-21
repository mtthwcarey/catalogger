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
    # Load descriptions from the batch file
    descriptions = load_descriptions(filename)
    logging.info(f"Loaded {len(descriptions)} descriptions from {filename}.")

    if not descriptions:
        logging.warning(f"No valid descriptions found in file: {filename}")
        return

    # Define the notes file path and ensure it is ready for writing
    notes_file = os.path.join(DATA_DIR, "entry_notes.txt")
    logging.info(f"Notes file will be saved to: {notes_file}")
    clear_or_create_notes_file(notes_file)

    # Process each description
    for idx, description in enumerate(descriptions, start=1):
        logging.info(f"Processing description {idx}/{len(descriptions)}...")  # Concise progress update
        process_single_description(idx, description, notes_file)

    logging.info("Batch processing completed successfully.")



def load_descriptions(filename):
    """Load book descriptions from file."""
    try:
        with open(filename, "r") as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
        print(f"File not found: {filename}")
        return []
    except Exception as e:
        logging.error(f"Error reading file {filename}: {e}")
        print(f"An error occurred while reading the file: {e}")
        return []


def clear_or_create_notes_file(notes_file):
    """Clear or create the entry notes file."""
    try:
        with open(notes_file, "w") as nf:
            nf.write("Entry Notes Log\n")
            nf.write("=" * 20 + "\n")
    except Exception as e:
        logging.error(f"Error creating notes file: {e}")
        print(f"An error occurred while setting up the notes file: {e}")


def process_single_description(index, description, notes_file):
    """Process a single book description."""
    logging.info(f"Processing book {index}: {description[:50]}...")

    notes = "No problems"

    # Extract book details
    try:
        book_details_text = parse_book_details(description)
        if not book_details_text:
            notes = "Could not extract book details"
            write_to_notes_file(index, description, notes, notes_file)
            return
    except Exception as e:
        notes = f"Error extracting details: {e}"
        write_to_notes_file(index, description, notes, notes_file)
        return

    # Parse details into a dictionary
    book_details = parse_book_details_to_dict(book_details_text)

    # Fetch metadata
    metadata_found = False
    try:
        metadata = fetch_metadata(book_details.get("Title", ""), book_details.get("Author", ""))
        if metadata:
            book_details.update(metadata)
            metadata_found = True
        else:
            notes = "Metadata not found"
            write_to_notes_file(index, description, notes, notes_file)
    except Exception as e:
        notes = f"Error fetching metadata: {e}"
        write_to_notes_file(index, description, notes, notes_file)

    # Add processing notes to the book details
    book_details["Notes"] = notes

    # Save details to CSV
    try:
        book_details["Index Number"] = f"{index:03}"
        book_details["Entry Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_to_csv(book_details)
        logging.info(f"Book {index}: Saved successfully.")
    except Exception as e:
        notes = f"Error saving to CSV: {e}"
        write_to_notes_file(index, description, notes, notes_file)


def write_to_notes_file(index, description, notes, notes_file):
    """Write problematic entries to the notes file."""
    entry_note = f"Book {index}:\n{notes}\nOriginal Entry: {description}\n\n"
    try:
        with open(notes_file, "a") as nf:
            nf.write(entry_note)
        logging.info(f"Written to notes file: Book {index}")
    except Exception as e:
        logging.error(f"Failed to write to notes file: {e}")
        print(f"Error writing to notes file: {e}")

def parse_book_details_to_dict(book_details_text):
    """Parse extracted book details into a dictionary."""
    book_details = {}
    for line in book_details_text.split("\n"):
        try:
            key, value = line.split(":", 1)
            book_details[key.strip().lstrip("-").strip()] = value.strip()
        except ValueError:
            logging.warning(f"Malformed line in book details: {line}")
    return book_details


def handle_entry_failure(index, description, reason, notes_file):
    """Handle failures during book processing."""
    entry_note = f"Skipped book {index}: {reason}"
    print(entry_note)
    logging.warning(entry_note)
    try:
        with open(notes_file, "a") as nf:
            nf.write(f"{entry_note} - Description: {description[:50]}...\n")
    except Exception as e:
        logging.error(f"Failed to write to notes file: {e}")


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

