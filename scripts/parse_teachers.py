"""
Parse teacher names from 'SLG - Contact List (1).docx' into structured JSON.

Extracts only "Lausanne Teachers" and "Online Teachers" sections.
Handles accented names, multi-person lines, and deduplication.

Usage:
    python scripts/parse_teachers.py
    python scripts/parse_teachers.py --docx "path/to/other.docx"

Output:
    data/teachers.json
"""

import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

# Fix Windows console encoding for accented characters
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import docx


# Regex for email addresses
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Regex for phone numbers:
# - International: +XX... (7-22 digits/spaces after +)
# - Swiss local: 0XX XXX XX XX (exactly 10 digits with optional spaces)
PHONE_RE = re.compile(r"(?:\+[\d\s()-]{7,22})|(?:0\d{2}[\s]?\d{3}[\s]?\d{2}[\s]?\d{2})")

# Known tag keywords that appear after the phone/email
TAG_KEYWORDS = [
    "ESA", "SFS", "WSE", "Junior", "JNR", "Fide", "Examinatrice", "Coordinator",
]


def normalize_whitespace(text):
    """Collapse tabs and multiple spaces into single spaces."""
    return re.sub(r"[\t ]+", " ", text).strip()


def extract_tags(text):
    """Extract school/role tags from the trailing portion of a line."""
    tags = []
    upper = text.upper()
    if "ESA" in upper:
        tags.append("ESA")
    if "SFS" in upper:
        tags.append("SFS")
    if "WSE" in upper:
        tags.append("WSE")
    if "JUNIOR" in upper or "JNR" in upper:
        tags.append("Junior")
    if "FIDE" in upper:
        if "EXAMINATRICE" in upper:
            tags.append("Fide Examinatrice")
        else:
            tags.append("Fide")
    if "COORDINATOR" in upper:
        tags.append("Coordinator")
    return tags


def parse_person(text, section):
    """Parse a single person entry from a line of text.

    Returns a dict with: firstname, lastname, phone, email, tags, section, source_line
    """
    source_line = text.strip()
    normalized = normalize_whitespace(text)

    # Extract email
    email_match = EMAIL_RE.search(normalized)
    email = email_match.group(0) if email_match else None

    # Extract phone(s)
    phones = PHONE_RE.findall(normalized)
    phone = phones[0].strip() if phones else None

    # Extract tags from the end of the line
    tags = extract_tags(normalized)

    # The name is the leading part before the first phone number or email
    # Remove everything after the name
    name_part = normalized
    # Cut at first phone number
    if phone:
        idx = name_part.find(phone.strip()[:5])  # match start of phone
        if idx > 0:
            name_part = name_part[:idx]
    # Cut at email
    if email:
        idx = name_part.find(email)
        if idx > 0:
            name_part = name_part[:idx]

    name_part = name_part.strip().rstrip("\t .-")

    # Split into first/last name
    name_parts = name_part.split()
    if len(name_parts) >= 2:
        firstname = name_parts[0]
        lastname = " ".join(name_parts[1:])
    elif len(name_parts) == 1:
        firstname = name_parts[0]
        lastname = ""
    else:
        return None

    # Clean up lastname edge cases like trailing punctuation
    lastname = lastname.strip().rstrip(".")

    return {
        "firstname": firstname,
        "lastname": lastname,
        "phone": phone,
        "email": email,
        "tags": tags,
        "section": section,
        "source_line": source_line,
    }


def split_morgan_jacqueline_line(text):
    """Handle the special two-person line:
    'Morgan Dalin +817089070288 morgan.dalin@gmail.com SFS Jacqueline Anderson +30 693 024 83 75 jacquel.anderson7@gmail.com WSE'
    """
    # Look for pattern: after first tag block, a new name starts (capital letter name)
    # Strategy: split on "Jacqueline" since we know the data
    # More robustly: find all emails and names
    emails = EMAIL_RE.findall(text)
    if len(emails) < 2:
        return [text]

    # Split at the second person's name: find where "Jacqueline" starts
    # Use the position right after the first tag block
    # Find all tag positions
    second_email = emails[1]
    second_email_pos = text.find(second_email)

    # Walk backwards from second email to find the start of the second name
    before_second = text[:second_email_pos].rstrip()
    # Find the phone number before the second email
    phones_before = PHONE_RE.findall(before_second)
    if phones_before:
        last_phone = phones_before[-1]
        phone_pos = before_second.rfind(last_phone.strip()[:5])
        # The name starts before this phone — scan backwards for tag keywords
        # Actually, let's find where the first person's tags end
        # The second person's name is between the first person's tags and the second phone

    # Simpler approach: split on known pattern — two emails means two people
    # Find the boundary: after first email + tags, before second person's name
    first_email_end = text.find(emails[0]) + len(emails[0])
    remaining = text[first_email_end:]

    # Find where a capitalized name starts (after optional whitespace and tags)
    name_match = re.search(r"\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+\+)", remaining)
    if name_match:
        split_pos = first_email_end + name_match.start()
        part1 = text[:split_pos].strip()
        part2 = remaining[name_match.start():].strip()
        return [part1, part2]

    # Fallback: split on the tag between them
    # Try splitting on "SFS" followed by a name
    tag_split = re.search(r"(SFS|WSE|ESA)\s+([A-Z][a-z]+\s+[A-Z])", remaining)
    if tag_split:
        split_pos = first_email_end + tag_split.start() + len(tag_split.group(1))
        part1 = text[:split_pos].strip()
        part2 = text[split_pos:].strip()
        return [part1, part2]

    return [text]


def parse_docx(docx_path):
    """Parse the contact list .docx and extract teachers."""
    doc = docx.Document(docx_path)

    teachers = []
    current_section = None
    target_sections = {"Lausanne Teachers": "lausanne", "Online Teachers": "online"}

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Check if this is a heading that starts/ends a section
        if para.style.name.startswith("Heading"):
            if text in target_sections:
                current_section = target_sections[text]
            else:
                # A different heading — we've left the section
                current_section = None
            continue

        # Only process lines in target sections
        if current_section is None:
            continue

        # Handle the two-person line (Morgan Dalin + Jacqueline Anderson)
        emails_in_line = EMAIL_RE.findall(text)
        if len(emails_in_line) >= 2:
            parts = split_morgan_jacqueline_line(text)
            for part in parts:
                person = parse_person(part, current_section)
                if person:
                    teachers.append(person)
            continue

        person = parse_person(text, current_section)
        if person:
            teachers.append(person)

    return teachers


def dedup_key(teacher):
    """Generate a deduplication key from normalized name."""
    fn = unicodedata.normalize("NFKD", teacher["firstname"].lower())
    fn = "".join(c for c in fn if not unicodedata.combining(c))
    ln = unicodedata.normalize("NFKD", teacher["lastname"].lower())
    ln = "".join(c for c in ln if not unicodedata.combining(c))
    return f"{fn}|{ln}"


def deduplicate(teachers):
    """Remove duplicate teachers, keeping the first occurrence but merging tags."""
    seen = {}
    result = []
    for t in teachers:
        key = dedup_key(t)
        if key in seen:
            # Merge tags
            existing = seen[key]
            for tag in t["tags"]:
                if tag not in existing["tags"]:
                    existing["tags"].append(tag)
            # Prefer non-null email/phone
            if t["email"] and not existing["email"]:
                existing["email"] = t["email"]
            if t["phone"] and not existing["phone"]:
                existing["phone"] = t["phone"]
        else:
            seen[key] = t
            result.append(t)
    return result


def print_summary(teachers):
    """Print a human-readable summary of parsed teachers."""
    print(f"\nTotal teachers: {len(teachers)}")

    by_section = {}
    for t in teachers:
        by_section.setdefault(t["section"], []).append(t)
    print("\nBy section:")
    for section, members in sorted(by_section.items()):
        print(f"  {section}: {len(members)}")

    tag_counts = {}
    for t in teachers:
        for tag in t["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    print("\nBy tag:")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count}")

    # Show teachers with no tags
    no_tags = [t for t in teachers if not t["tags"]]
    if no_tags:
        print(f"\nTeachers with no tags: {len(no_tags)}")
        for t in no_tags:
            print(f"  {t['firstname']} {t['lastname']}")

    # Show teachers with email
    with_email = [t for t in teachers if t["email"]]
    print(f"\nTeachers with email: {len(with_email)}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Parse teacher names from .docx to JSON")
    parser.add_argument(
        "--docx",
        default="SLG - Contact List (1).docx",
        help="Path to the contact list .docx file",
    )
    parser.add_argument(
        "--output",
        default="data/teachers.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).resolve().parent.parent
    docx_path = project_root / args.docx
    output_path = project_root / args.output

    if not docx_path.exists():
        print(f"Error: .docx file not found at {docx_path}")
        return 1

    print(f"Parsing: {docx_path.name}")
    teachers = parse_docx(str(docx_path))
    print(f"Extracted {len(teachers)} entries before deduplication")

    teachers = deduplicate(teachers)
    print(f"After deduplication: {len(teachers)} teachers")

    print_summary(teachers)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(teachers, f, indent=2, ensure_ascii=False)
    print(f"Written to: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
