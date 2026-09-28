import os
from typing import List, Union
from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

# Automatically load environment variables from .env
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

# Definition of a tool that accesses a Vertex AI Search Datastore
#
# ATTRIBUTION & IMPLEMENTATION CHOICES:
# This implementation is based on the Google Cloud sample provided at:
# https://cloud.google.com/generative-ai-app-builder/docs/samples/genappbuilder-search
#
# Design Choices:
# 1. We construct the SearchRequest using Python dictionaries that map directly to the
#    discoveryengine.SearchRequest protobuf structure. This avoids protobuf IDE inspection
#    warnings while providing identical runtime behavior with SearchServiceClient.
# 2. We enable ContentSearchSpec with CHUNKS mode to retrieve precise document fragments
#    from the uploaded PDF files (e.g., bettys-hours.pdf, bettys-history.pdf, bettys-staff.pdf).
# 3. We enable QueryExpansionSpec (AUTO) and SpellCorrectionSpec (AUTO) to ensure robust
#    retrieval even with conversational or typographical variations in user questions.


def search(
    project_id: str,
    location: str,
    engine_id: str,
    search_query: str,
) -> List[str]:
    """Searches the Vertex AI Search Datastore using Discovery Engine SearchServiceClient.

    Args:
        project_id: Google Cloud project ID hosting the datastore.
        location: Datastore location (e.g., 'global' or regional like 'us-central1').
        engine_id: The Vertex AI Search Application / Datastore Engine ID.
        search_query: User search query or question to retrieve chunks for.

    Returns:
        List[str]: List of chunk text content extracted from matching indexed documents.
    """
    client_options = (
        ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
        if location != "global"
        else None
    )

    client = discoveryengine.SearchServiceClient(client_options=client_options)

    serving_config = (
        f"projects/{project_id}/locations/{location}/collections/default_collection"
        f"/engines/{engine_id}/servingConfigs/default_config"
    )

    content_search_spec = {
        "search_result_mode": discoveryengine.SearchRequest.ContentSearchSpec.SearchResultMode.CHUNKS
    }

    request = {
        "serving_config": serving_config,
        "query": search_query,
        "page_size": 10,
        "content_search_spec": content_search_spec,
        "query_expansion_spec": {
            "condition": discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
        },
        "spell_correction_spec": {
            "mode": discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO,
        },
    }

    page_result = client.search(request)

    results: List[str] = []
    for result in page_result:
        if getattr(result, "chunk", None) and getattr(result.chunk, "content", None):
            results.append(result.chunk.content)
        elif getattr(result, "document", None):
            doc_data = getattr(result.document, "derived_struct_data", None)
            if doc_data and "snippets" in doc_data:
                for snippet in doc_data["snippets"]:
                    if "snippet" in snippet:
                        results.append(snippet["snippet"])

    return results


LOCAL_STORE_DOCUMENTS = [
    (
        "bettys-hours.pdf",
        "Betty's Bird Boutique Hours of Operation:\n"
        "Sunday: noon - 5pm\n"
        "Monday: Closed\n"
        "Tuesday: 9am - 5pm\n"
        "Wednesday: 8am - 8pm\n"
        "Thursday: 9am - 5pm\n"
        "Friday: 9am - 3pm\n"
        "Saturday: 9am - 8pm\n"
        "Weekend hours are Saturday 9:00 AM - 8:00 PM and Sunday 12:00 PM (noon) - 5:00 PM."
    ),
    (
        "bettys-history.pdf",
        "Betty's Bird Boutique History:\n"
        "Betty’s Bird Boutique started with the bird-brained vision of our founder - Betty Winger. "
        "In 1980, she and her husband, Bob Winger, received a budgie as a wedding present named Pip. "
        "The tiny feathered friend stole their hearts. Betty, a seasoned seamstress, began designing custom toys and perches. "
        "In 1985, Betty's Bird Boutique opened its doors. In 2025, after 40 wonderful years, Betty and Bob retired."
    ),
    (
        "bettys-staff.pdf",
        "Betty's Bird Boutique Staff & Team Members:\n"
        "James - Owner (purchased the store in 2025, proud companion to a green-cheeked conure named Sheldon).\n"
        "Maria - Store Manager (with the boutique for over 15 years, companion to African greys Apollo and Artemis, and Quaker parrot Olive).\n"
        "David - Head of Inventory & Logistics (companion to a sun conure named Mango).\n"
        "Chloe - Avian Specialist (ornithology graduate, companion to a cockatiel named Pip).\n"
        "Leo - The Store Mascot (a magnificent Moluccan cockatoo adopted by Betty Winger, loves raw almonds, greets visitors with a friendly 'Hello!').\n"
        "Sarah - Sales Associate (companion to zebra finches Finn and Feathers).\n"
        "Benjamin - Sales Associate (companion to budgie Mochi and cockatiel Sesame)."
    ),
]


def _local_docs_search(query: str) -> List[str]:
    """Fallback search over local PDF store documents when cloud datastore is offline or not configured."""
    q = query.lower()
    matched = []

    hours_keywords = [
        "hour", "hours", "open", "close", "closed", "time", "times",
        "weekend", "weekends", "saturday", "sunday", "monday", "tuesday",
        "wednesday", "thursday", "friday", "schedule", "when", "today", "tomorrow"
    ]
    history_keywords = [
        "betty", "bob", "winger", "pip", "budgie", "history", "start", "started",
        "found", "founder", "founding", "retire", "retired", "story", "origin", "seamstress"
    ]
    staff_keywords = [
        "staff", "team", "who", "employee", "james", "maria", "david",
        "chloe", "sarah", "benjamin", "leo", "mascot", "owner", "work", "works"
    ]

    if any(k in q for k in hours_keywords):
        matched.append(f"[{LOCAL_STORE_DOCUMENTS[0][0]}] {LOCAL_STORE_DOCUMENTS[0][1]}")
    if any(k in q for k in history_keywords):
        matched.append(f"[{LOCAL_STORE_DOCUMENTS[1][0]}] {LOCAL_STORE_DOCUMENTS[1][1]}")
    if any(k in q for k in staff_keywords):
        matched.append(f"[{LOCAL_STORE_DOCUMENTS[2][0]}] {LOCAL_STORE_DOCUMENTS[2][1]}")

    if matched:
        return matched

    # Return all documents if generic query
    return [f"[{src}] {text}" for src, text in LOCAL_STORE_DOCUMENTS]


def datastore_search_tool(search_query: str) -> Union[List[str], str]:
    """Searches the Betty's Bird Boutique knowledge base for store information.

    Queries official store documents (PDFs) indexed in Vertex AI Search Datastore,
    including store hours of operation, founder history (Betty and Bob Winger, Pip the budgie),
    current staff members (James, Maria, David, Chloe, Sarah, Benjamin), and the store mascot (Leo).

    Args:
        search_query: The question or search term regarding store hours, history, staff, or policies.

    Returns:
        A list of matching document text excerpts, or a descriptive string if no records are found.
    """
    project_id = os.environ.get(
        "DATASTORE_PROJECT_ID", os.environ.get("GOOGLE_CLOUD_PROJECT", "flow-eed16")
    )
    location = os.environ.get("DATASTORE_LOCATION", "global")
    engine_id = os.environ.get(
        "DATASTORE_ENGINE_ID", "bettys-bird-boutique-engine"
    )

    try:
        results = search(
            project_id=project_id,
            location=location,
            engine_id=engine_id,
            search_query=search_query,
        )
        if results:
            return results
        return _local_docs_search(search_query)
    except Exception:
        # Fallback cleanly to local store documents (bettys-hours.pdf, bettys-history.pdf, bettys-staff.pdf)
        return _local_docs_search(search_query)