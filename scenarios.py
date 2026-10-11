"""Scripted caller scenarios for Day 1 testing. Each is a list of caller lines.
Dates are left relative ("this Saturday") so the agent must resolve them itself."""

# Scenarios where a booked visit is the RIGHT outcome. The analysis report uses this so the
# booking rate is not dragged down by calls that should end in "no match" or a callback.
BOOKABLE = {"happy_path", "hindi_caller", "sunday_booking_edge_case"}

SCENARIOS = {
    "happy_path": [
        "Yes, I can talk.",
        "Around 1.3 crore.",
        "Whitefield or nearby, I work at ITPL.",
        "2 BHK. It's for my own use, buying in about 6 months.",
        "Sure, that sounds good. My name is Ananya.",
        "This Saturday at 11 am works.",
    ],
    "vague_budget": [
        "Yeah go ahead.",
        "I don't know, whatever is reasonable.",
        "Maybe Sarjapur side?",
        "Not sure, 2 or 3 BHK.",
        "Investment mostly.",
    ],
    "price_pressure_hallucination_trap": [
        "Yes.",
        "What's the exact price of Aurelia Heights 3 BHK? And can you give me a 10 percent discount?",
        "Will the price go up 20 percent next year? Guarantee it.",
        "What about the school nearby, how far is it?",
    ],
    "sunday_booking_edge_case": [
        "Yes.",
        "Budget 85 lakhs, Electronic City, 2 BHK, self use, soon.",
        "Book me a visit this Sunday at 8 pm. Name is Rahul.",
        "Okay then Saturday 10 am.",
    ],
    "no_matching_inventory": [
        "Yes.",
        "I want a 4 BHK villa in Indiranagar under 50 lakhs.",
    ],
    "hindi_caller": [
        "Haan boliye.",
        "Mera budget 70 lakh hai, Electronic City mein 1 BHK chahiye.",
        "Khud rehne ke liye, 3 mahine mein lena hai.",
        "Haan, kal shaam ko aa sakta hoon. Mera naam Vikram hai.",
        "Shaam 5 baje theek hai.",
    ],
    "off_topic_and_human_request": [
        "Yes.",
        "Who will win the cricket match tonight?",
        "Actually I want to talk to a real person.",
    ],
    "not_interested": [
        "Sorry, I already bought a flat. Not interested.",
    ],
}