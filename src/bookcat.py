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
        text = recognizer.recognize_google(audio)
        logging.info(f"Recognized speech: {text}")
        return text
    except sr.UnknownValueError:
        logging.warning("Speech was not understood. Please try again.")
        return None
    except sr.RequestError as e:
        logging.error(f"Error with the Google Speech Recognition API: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during speech recognition: {e}")
        return None

def parse_book_details(description):
    """Extract book details using OpenAI's ChatCompletion API."""
    if not description:
        logging.error("Empty description passed to parse_book_details.")
        return None

    prompt = f"""
    Extract the following details from this book description: 
    - Title
    - Author
    - Format (e.g., hardcover, paperback)
    - Year

    Description: {description}
    """
    try:
        # Log the prompt for debugging
        logging.debug(f"Prompt sent to OpenAI: {prompt.strip()}")

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that extracts book details from text."},
                {"role": "user", "content": prompt}
            ]
        )

        # Extract and log the raw response from OpenAI
        raw_response = response['choices'][0]['message']['content'].strip()
        logging.debug(f"Raw response from OpenAI: {raw_response}")

        # Log the book details for transparency
        logging.info(f"Book details extracted: {raw_response}")

        return raw_response
    except Exception as e:
        logging.error(f"Error with OpenAI API: {e}")
        return None

def parse_book_details_to_dict(details_text):
    """
    Convert structured book details (string) into a dictionary.
    Handles inconsistencies such as missing dashes, extra whitespace, or malformed lines.
    """
    details_dict = {}
    try:
        # Normalize lines to handle leading dashes and extra spaces
        normalized_lines = [
            line.strip().lstrip("-").strip() for line in details_text.splitlines() if line.strip()
        ]

        for line in normalized_lines:
            if ":" in line:  # Ensure it's a valid key-value pair
                key, value = line.split(":", 1)  # Split at the first colon
                key, value = key.strip(), value.strip()  # Remove extra whitespace
                if key and value:  # Only add valid key-value pairs
                    details_dict[key] = value
            else:
                logging.warning(f"Skipping unrecognized line: {line}")

        logging.debug(f"Parsed book details into dictionary: {details_dict}")
        return details_dict
    except Exception as e:
        logging.error(f"Error parsing book details to dictionary: {e}")
        return {}


def fetch_metadata(title, author, retries=3, pause=1):
    """Fetch additional metadata from Google Books API with error logging."""
    api_url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"intitle:{title}+inauthor:{author}",
        "maxResults": 1
    }

    for attempt in range(1, retries + 1):
        try:
            logging.info(f"Fetching metadata for Title: '{title}', Author: '{author}' (Attempt {attempt})")
            response = requests.get(api_url, params=params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)

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
                logging.warning(f"No metadata found for Title: '{title}', Author: '{author}'.")
                return None

        except requests.exceptions.RequestException as e:
            # Log detailed error response
            if response := e.response:  # Only if the exception contains a response
                try:
                    error_message = response.json().get("error", {}).get("message", "Unknown error")
                    logging.error(f"API Error: {response.status_code} - {error_message}")
                except ValueError:
                    # Fallback if the response isn't JSON
                    logging.error(f"API Error: {response.status_code} - {response.text}")
            else:
                logging.error(f"Request error: {e}")

            # Retry mechanism
            if attempt < retries:
                logging.info(f"Retrying after {pause} seconds...")
                time.sleep(pause)
                pause *= 2  # Exponential backoff
            else:
                logging.error(f"Failed to fetch metadata after {retries} attempts.")
                return None

def save_to_csv(book_details, filename=OUTPUT_FILE, quiet=True):
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

        # Add the "Error Notes" column if it's not present
        if "Error Notes" not in book_details:
            book_details["Error Notes"] = "No problems"

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

        if not quiet:
            print(f"Book details saved to {filename}")
    except Exception as e:
        logging.error(f"Error saving to CSV: {e}")

def process_single_description(index, description, notes_file):
    """
    Process a single book description and handle problematic entries.
    """
    if not description:
        notes = "Empty description"
        write_to_notes_file(index, "No description provided", notes, notes_file)
        logging.warning(f"Book {index}: Skipped due to empty description.")
        return {"Index Number": index, "Error Notes": notes}

    logging.info(f"Processing book {index}: {description[:50]}...")
    notes = "No problems"

    # Extract book details
    try:
        book_details_text = parse_book_details(description)
        logging.debug(f"Raw details extracted: {book_details_text}")
        
        if not book_details_text or "Title:" not in book_details_text or "Author:" not in book_details_text:
            notes = "Malformed details format"
            write_to_notes_file(index, description, notes, notes_file)
            logging.warning(f"Book {index}: Missing expected fields in extracted details: {book_details_text}")
            return {"Index Number": index, "Error Notes": notes}

        book_details = parse_book_details_to_dict(book_details_text)
        if not book_details.get("Title") or not book_details.get("Author"):
            notes = "Missing title or author in parsed details"
            write_to_notes_file(index, description, notes, notes_file)
            logging.warning(f"Book {index}: Missing title or author in parsed dictionary: {book_details}")
            return {"Index Number": index, "Error Notes": notes}
    except Exception as e:
        notes = f"Error extracting details: {e}"
        write_to_notes_file(index, description, notes, notes_file)
        logging.error(f"Book {index}: Error extracting details - {e}")
        return {"Index Number": index, "Error Notes": notes}

    # Fetch metadata
    try:
        metadata = fetch_metadata(book_details["Title"], book_details["Author"])
        if metadata:
            book_details.update(metadata)
            logging.info(f"Book {index}: Metadata fetched successfully.")
        else:
            notes = "Metadata not found"
            write_to_notes_file(index, description, notes, notes_file)
            logging.warning(f"Book {index}: Metadata not found.")
    except Exception as e:
        notes = f"Error fetching metadata: {e}"
        write_to_notes_file(index, description, notes, notes_file)
        logging.error(f"Book {index}: Error fetching metadata - {e}")

    # Save details to CSV
    try:
        book_details["Index Number"] = f"{index:03}"
        book_details["Entry Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        book_details["Error Notes"] = notes  # Add notes to the book details
        save_to_csv(book_details)
        logging.info(f"Book {index}: Saved successfully.")
    except Exception as e:
        notes = f"Error saving to CSV: {e}"
        write_to_notes_file(index, description, notes, notes_file)
        logging.error(f"Book {index}: Error saving to CSV - {e}")
        return {"Index Number": index, "Error Notes": notes}

    return {"Index Number": index, "Error Notes": notes}

def process_batch_file(filename):
    """Process a text file containing multiple book descriptions."""
    logging.info(f"Starting batch file processing for: {filename}")

    # Add this debug statement
    if not os.path.isfile(filename):
        logging.error(f"File does not exist: {filename}")
        print(f"Error: File does not exist - {filename}")
        return

    try:
        descriptions = load_descriptions(filename)
        logging.info(f"Loaded {len(descriptions)} descriptions from {filename}.")
        print(f"Loaded {len(descriptions)} descriptions from {filename}.")

        if not descriptions:
            logging.warning(f"No valid descriptions found in file: {filename}")
            print("No valid descriptions found. Exiting.")
            return

        notes_file = os.path.join(DATA_DIR, "entry_notes.txt")
        with open(notes_file, "w") as nf:
            nf.write("Entry Notes Log\n")
            nf.write("=" * 20 + "\n")

        total_books = len(descriptions)
        print("Processing started...")

        for idx, description in enumerate(descriptions, start=1):
            if not description:
                logging.warning(f"Empty description for book {idx}. Skipping.")
                write_to_notes_file(idx, "Empty description", "No content", notes_file)
                continue

            process_single_description(idx, description, notes_file)
            print(f"\rProcessed {idx}/{total_books} books...", end="")

        print("\nProcessing complete!")

    except Exception as e:
        logging.error(f"Error during batch processing: {e}")
        print(f"Error: {e}")


def write_to_notes_file(index, description, notes, notes_file):
    """Write problematic entries to the notes file."""
    entry_note = f"Book {index}:\n{notes}\nOriginal Entry: {description}\n\n"
    try:
        with open(notes_file, "a") as nf:
            nf.write(entry_note)
        logging.info(f"Written to notes file: Book {index} - Notes: {notes}")
    except Exception as e:
        logging.error(f"Failed to write to notes file for Book {index}: {e}")

def load_descriptions(filename):
    """Load book descriptions from file."""
    try:
        with open(filename, "r") as file:
            descriptions = [line.strip() for line in file if line.strip()]
            logging.info(f"Successfully loaded {len(descriptions)} descriptions from {filename}.")
            return descriptions
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
        return []
    except Exception as e:
        logging.error(f"Error reading file {filename}: {e}")
        return []

# Other functions...

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

        description = None

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
        else:
            print("Invalid option. Returning to menu.")
            continue

        if not description:
            print("Description is empty or invalid. Returning to menu.")
            continue

        print("Extracting book details...")
        book_details_text = parse_book_details(description)
        if not book_details_text:
            print("Could not extract book details.")
            continue

        book_details = parse_book_details_to_dict(book_details_text)
        metadata = fetch_metadata(book_details.get("Title", ""), book_details.get("Author", ""))
        if metadata:
            book_details.update(metadata)

        save_to_csv(book_details)
        print("Book added successfully!")

# Ensure script runs correctly when executed directly
if __name__ == "__main__":
    main()


