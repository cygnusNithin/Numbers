
"""
Test draw lookup using a video filename.
"""

from draw_lookup import DrawLookup


filename = (
    "Kerala Lottery Official Live - SAMRUDHI "
    "- SM-70 - 30.08.2026.mp4"
)


lookup = DrawLookup()

try:
    # --------------------------------------------------
    # STEP 1: Extract serial from filename
    # --------------------------------------------------

    serial = lookup.extract_serial(filename)

    print("Extracted serial:", serial)

    # --------------------------------------------------
    # STEP 2: Find draw in absolute_data_v2
    # --------------------------------------------------

    draw = lookup.find_draw(serial)

    if draw is None:

        print("Draw not found in absolute_data_v2")

    else:

        # --------------------------------------------------
        # STEP 3: Display draw metadata
        # --------------------------------------------------

        print("\nDraw found:")

        print("Serial:", draw["serialNumber"])
        print("Date:", draw["date"])
        print("Draw category:", draw["drawCategory"])

        # --------------------------------------------------
        # STEP 4: Display prize categories
        # --------------------------------------------------

        print("\nPrize categories:")

        for category in draw["prizeCategories"]:

            print(
                f'{category["prizeCategory"]} '
                f'=> {category["prize"]} '
                f'| Numbers: {category["numberCount"]}'
            )

finally:

    lookup.close()
