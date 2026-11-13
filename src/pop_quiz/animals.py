"""Random animal names for participants."""

import random


_ADJECTIVES = [
    "Brave",
    "Cheerful",
    "Clumsy",
    "Cuddly",
    "Dancing",
    "Fluffy",
    "Friendly",
    "Funny",
    "Gentle",
    "Goofy",
    "Grumpy",
    "Happy",
    "Jolly",
    "Lazy",
    "Lively",
    "Mighty",
    "Sleepy",
    "Sneaky",
    "Sparkly",
    "Speedy",
]

_ANIMALS = [
    "🐯 Tiger",
    "🦊 Fox",
    "🐼 Panda",
    "🐨 Koala",
    "🦁 Lion",
    "🐮 Cow",
    "🐷 Pig",
    "🐸 Frog",
    "🐔 Chicken",
    "🐧 Penguin",
    "🦅 Eagle",
    "🦉 Owl",
    "🐺 Wolf",
    "🐻 Bear",
    "🐻‍❄️ Polar Bear",
    "🦄 Unicorn",
    "🐝 Bee",
    "🦋 Butterfly",
    "🐢 Turtle",
    "🐙 Octopus",
    "🦦 Otter",
    "🦥 Sloth",
    "🦨 Skunk",
    "🦔 Hedgehog",
    "🦘 Kangaroo",
    "🐹 Hamster",
    "🐰 Rabbit",
    "🐭 Mouse",
    "🐶 Dog",
    "🐱 Cat",
]


def random_animal_name() -> str:
    """Return a random animal name like 'Brave 🐯 Tiger'."""
    adjective = random.choice(_ADJECTIVES)
    index = random.randint(1, len(_ANIMALS) - 1)
    return f"{adjective} {_ANIMALS[index]}"
