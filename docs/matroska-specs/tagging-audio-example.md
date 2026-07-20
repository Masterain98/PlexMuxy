> **Source:** https://www.matroska.org/technical/tagging-audio-example.html
> Automated Markdown transcription of the official Matroska / MKVToolNix technical documentation, structured for AI-agent consumption. Original copyright of the respective authors / Matroska organization applies.

---

# Audio Tags Example

## Introduction

Audio content is usually found with tags, i.e. meta information about the content you can listen to like the artist name, the track title, the year of release, etc. The problem is that people are now ripping their CDs in just one file for consistency on their hard-drive and usually avoiding gap problems on live/classical/mixes albums. So now you can find many tracks in just one file, and the usual flat structure to tag content doesn’t work anymore.

The XML Tag files matching [mkvmerge’s DTD format](https://www.matroska.org/files/tags/matroskatags.dtd) for all the examples on this page can be found in a [zip file](https://dl.matroska.org/downloads/examples/audiotags.zip).

Let’s consider the mini-album of [The Micronauts](http://www.the-micronauts.com/) “[Bleep To Bleep](http://www.discogs.com/release/8788)”, as found in the chapter examples. The tracks are laid out on the CD as follows:

- 00:00 - 12:28 : Baby Wants To Bleep/Rock
   - **01**  - 00:00 - 04:38 : Baby wants to bleep (pt.1)
   - **02**  - 04:38 - 07:12 : Baby wants to rock
   - **03**  - 07:12 - 10:33 : Baby wants to bleep (pt.2)
   - **04**  - 10:33 - 12:28 : Baby wants to bleep (pt.3)
- **05**  - 12:30 - 19:38 : Bleeper_O+2
- **06**  - 19:40 - 22:20 : Baby wants to bleep (pt.4)
- **07**  - 22:22 - 25:18 : Bleep to bleep
- **08**  - 25:20 - 33:35 : Baby wants to bleep (k)
- **09**  - 33:37 - 44:28 : Bleeper

Tracks 01 to 04 are linked together and are actually making just one “virtual” track to the listener.

## One file with all tracks

In this case the file contains one continuous audio track of 44:28. Chapters are used to virtually split the content in many parts, ie the CD tracks. A basic ripping application would rip the CD tracks as follows :

- Chapters
   - EditionEntry
      - ChapterAtom
         - ChapterUID = 123456
         - ChapterTimeStart = 0 ns
         - ChapterTimeEnd = 278,000,000 ns
      - ChapterAtom
         - ChapterUID = 234567
         - ChapterTimeStart = 278,000,000 ns
         - ChapterTimeEnd = 432,000,000 ns
      - ChapterAtom
         - ChapterUID = 345678
         - ChapterTimeStart = 432,000,000 ns
         - ChapterTimeEnd = 633,000,000 ns
      - ChapterAtom
         - ChapterUID = 456789
         - ChapterTimeStart = 633,000,000 ns
         - ChapterTimeEnd = 748,000,000 ns
      - ChapterAtom
         - ChapterUID = 567890
         - ChapterTimeStart = 750,000,000 ns
         - ChapterTimeEnd = 1,178,500,000 ns
      - ChapterAtom
         - ChapterUID = 678901
         - ChapterTimeStart = 1,180,000,000 ns
         - ChapterTimeEnd = 1,340,000,000 ns
      - ChapterAtom
         - ChapterUID = 789012
         - ChapterTimeStart = 1,342,000,000 ns
         - ChapterTimeEnd = 1,518,000,000 ns
      - ChapterAtom
         - ChapterUID = 890123
         - ChapterTimeStart = 1,520,000,000 ns
         - ChapterTimeEnd = 2,015,000,000 ns
      - ChapterAtom
         - ChapterUID = 901234
         - ChapterTimeStart = 2,017,000,000 ns
         - ChapterTimeEnd = 2,668,000,000 ns

Now let’s see how a basic tagging of this file would work ([XML version](https://www.matroska.org/files/tags/bleep-one.xml)) :

- Tags
   - Tag
      - Targets ( *no target means the whole content of the file, otherwise you can put all ChapterUIDs* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Micronauts”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep To Bleep”
      - SimpleTag
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “9”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2004-04”
   - Tag
      - Targets
         - ChapterUID = 123456
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.1)”
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
   - Tag
      - Targets
         - ChapterUID = 234567
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to rock”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “2”
   - Tag
      - Targets
         - ChapterUID = 345678
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.2)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “3”
   - Tag
      - Targets
         - ChapterUID = 456789
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.3)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “4”
   - Tag
      - Targets
         - ChapterUID = 567890
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleeper_O+2”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “5”
   - Tag
      - Targets
         - ChapterUID = 678901
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.4)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “6”
   - Tag
      - Targets
         - ChapterUID = 789012
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep to bleep”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “7”
   - Tag
      - Targets
         - ChapterUID = 890123
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (k)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “8”
   - Tag
      - Targets
         - ChapterUID = 901234
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleeper”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “9”

## One file per CD track

Now let’s split this one file in pieces :

### Track 1 / File #1

[XML version](https://www.matroska.org/files/tags/bleep-trackfile1.xml)

- Tags
   - Tag
      - Targets (no target means the whole content of the file, otherwise you can put all ChapterUIDs)
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Micronauts”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep To Bleep”
      - SimpleTag
         - TagName = “TOTAL_PARTS”
         - TagString = “9”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2004-04”
   - Tag
      - Targets ( *no chapter target since the file may not contain one, but if it does you can use it* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.1)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “1”

### Track 2 / File #2

[XML version](https://www.matroska.org/files/tags/bleep-trackfile2.xml)

- Tags
   - Tag
      - Targets (no target means the whole content of the file, otherwise you can put all ChapterUIDs)
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Micronauts”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep To Bleep”
      - SimpleTag
         - TagName = “TOTAL_PARTS”
         - TagString = “9”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2004-04”
   - Tag
      - Targets ( *no chapter target since the file may not contain one, but if it does you can use it* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to rock”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “2”

etc…

## One file per “meaningful” track

In this case the 4 first tracks appear in one file.

### Tracks 1-2-3-4 / File #1

[XML version](https://www.matroska.org/files/tags/bleep-continuous1.xml)

- Tags
   - Tag
      - Targets (no target means the whole content of the file, otherwise you can put all ChapterUIDs)
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Micronauts”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep To Bleep”
      - SimpleTag
         - TagName = “TOTAL_PARTS”
         - TagString =  *“6”*
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2004-04”
   - Tag
      - Targets ( *include all chapters that match the first 4 tracks, if chapters are present in the file* )
         - ChapterUID = 123456
         - ChapterUID = 234567
         - ChapterUID = 345678
         - ChapterUID = 456789
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString =  *“Baby wants to bleep/rock”*
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “1”
      - SimpleTag
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “4”
   - Tag ( *the following tags may or may not be included in the file, it can’t be if no chapters are used* )
      - Targets
         - ChapterUID = 123456
         - *TargetTypeValue = 20*
         - *TargetType = “PART”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.1)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “1”
   - Tag
      - Targets
         - ChapterUID = 234567
         - *TargetTypeValue = 20*
         - *TargetType = “PART”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to rock”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “2”
   - Tag
      - Targets
         - ChapterUID = 345678
         - *TargetTypeValue = 20*
         - *TargetType = “PART”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.2)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “3”
   - Tag
      - Targets
         - ChapterUID = 456789
         - *TargetTypeValue = 20*
         - *TargetType = “PART”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Baby wants to bleep (pt.3)”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “4”

### Tracks 5 / File #2

[XML version](https://www.matroska.org/files/tags/bleep-continuous2.xml)

- Tags
   - Tag
      - Targets (no target means the whole content of the file, otherwise you can put all ChapterUIDs)
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Micronauts”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleep To Bleep”
      - SimpleTag
         - TagName = “TOTAL_PARTS”
         - TagString =  *“6”*
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2004-04”
   - Tag
      - Targets ( *no chapter target since the file may not contain one, but if it does you can use it* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Bleeper_O+2”
      - SimpleTag
         - TagName = “PART_NUMBER”
         - TagString = “2”

etc…

## Album on 2 CDs

Many albums contain 2 CD in the box. Here is an example of a real-life case and how to keep the information about the physical source: Future Sound Of London “[Lifeforms](http://www.discogs.com/release/8067)”. In this example we’ll have one file per CD track.

### File #1 : CD #1 - Track #1

[XML version](https://www.matroska.org/files/tags/lifeform-1_1.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Lifeforms”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Future Sound Of London”
      - SimpleTag ( *the number of tracks in the album* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “19”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1994”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Virgin Records UK”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *the number of the track in the album* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Cascade”

### File #2 : CD #1 - Track #2

[XML version](https://www.matroska.org/files/tags/lifeform-1_2.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Lifeforms”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Future Sound Of London”
      - SimpleTag ( *the number of tracks in the album* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “19”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1994”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Virgin Records UK”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *the number of the track in the album* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Ill Flower”

etc…

### File #9 : CD #2 - Track #1

[XML version](https://www.matroska.org/files/tags/lifeform-2_1.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Lifeforms”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Future Sound Of London”
      - SimpleTag ( *the number of tracks in the album* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “19”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1994”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Virgin Records UK”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *the number of the track in the album* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “9”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Domain”

etc…

## Album with 2 different CDs

This is almost the same as the previous example. But this time each CD in the pack is related to a different logical level: DJ Hell “[Electronicbody-Housemusic](http://www.discogs.com/release/63287)”. In this example we’ll have one file per CD track.

### File #1 : CD #1 - Track #1

[XML version](https://www.matroska.org/files/tags/hell-eh-1_1.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Electronicbody-Housemusic”
      - SimpleTag
         - TagName = “MIXED_BY”
         - TagString = “DJ Hell”
      - SimpleTag ( *the number of parts in the album : 2 sessions* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “2”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2002-10-28”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “React”
   - Tag ( *information about the 1st session CD* )
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 40*
         - *TargetType = “SESSION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Housemusic”
      - SimpleTag ( *the number of the session* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of tracks in the session* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “18”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *the number of the track in the album* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Underground Resistance”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Inspiration”

### File #2 : CD #1 - Track #2

[XML version](https://www.matroska.org/files/tags/hell-eh-1_2.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Electronicbody-Housemusic”
      - SimpleTag
         - TagName = “MIXED_BY”
         - TagString = “DJ Hell”
      - SimpleTag ( *the number of parts in the album : 2 sessions* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “2”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2002-10-28”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “React”
   - Tag ( *information about the 1st session CD* )
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 40*
         - *TargetType = “SESSION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Housemusic”
      - SimpleTag ( *the number of the session* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of tracks in the session* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “18”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *2 of 18* )
         - TagName = “PART_NUMBER”
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Metro Area”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Miura”

etc… Now from second CD/mix :

### File #19 : CD #2 - Track #1

[XML version](https://www.matroska.org/files/tags/hell-eh-2_1.xml)

- Tags
   - Tag
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Electronicbody-Housemusic”
      - SimpleTag
         - TagName = “MIXED_BY”
         - TagString = “DJ Hell”
      - SimpleTag ( *the number of parts in the album : 2 sessions* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “2”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “2002-10-28”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “React”
   - Tag ( *information about the 1st session CD* )
      - Targets ( *no target since it covers the whole file and more* )
         - *TargetTypeValue = 40*
         - *TargetType = “SESSION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Electronicbody”
      - SimpleTag ( *2 of 2* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag ( *the number of tracks in the session* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “16”
   - Tag
      - Targets ( *no target since it covers the whole file* )
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag ( *1 of 16* )
         - TagName = “PART_NUMBER”
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “German Broadcaster”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “S-Channel”
      - SimpleTag
         - TagName = “SUBTITLE”
         - TagString = “Radio Broadcast Mix”

etc…

## Collection of CD sets

Sometimes an album can contain many CDs. And sometimes an album can be part of a bigger collection, like a CD series. Here is one example of such a real-life case and how it would be tagged. We’ll **only cover the case of 1 file per CD**. Other cases could be deduced from the previous examples.

The example here is a Big Beat collection called “Big Beat Elite” by the Lacerba label. There are 3 instances in this collection : “[Big Beat Elite](http://www.discogs.com/release/70919)”, “[Big Beat Elite Repeat](http://www.discogs.com/release/72561)” and “[Big Beat Elite Complete](http://www.discogs.com/release/157518)”. Each item in the collection contains 3 CDs. 2 CDs containing the tracks, and the 3rd CD containing the same tracks but mixed. We won’t tag all the content here, just giving examples how some CDs or tracks would be tagged in the file.

### File #1 : Big Beat Elite CD #1 containing plain tracks

[XML version](https://www.matroska.org/files/tags/bigbeat-1_1.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of the set in the collection* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1997”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “10”
   - Tag
      - Targets ( *the first track of the first CD* )
         - ChapterUID = 123456
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Sol Brothers”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “That Elvis Track”
   - Tag
      - Targets ( *the second track of the CD is a remix* )
         - ChapterUID = 234567
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Saint Etienne”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Filthy”
      - SimpleTag
         - TagName =  *“SUBTITLE”*
         - TagString = “Monkey Mafia Mix”
      - SimpleTag
         - TagName =  *“REMIXED_BY”*
         - TagString = “Monkey Mafia”
   - etc…

### File #2 : Big Beat Elite CD #2 containing plain tracks

[XML version](https://www.matroska.org/files/tags/bigbeat-1_2.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag ( *this tag may be omitted as it’s the same as the upper level, but it wouldn’t be coherent with other CDs* )
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of the set in the collection* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1997”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “10”
   - Tag
      - Targets ( *the first track of the CD* )
         - ChapterUID = 987654
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Bentley Rhythm Ace”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Run On The Spot”
   - Tag
      - Targets ( *the second track of the CD* )
         - ChapterUID = 876543
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Eboman”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Donuts With Buddah”
   - etc…

### File #3 : Big Beat Elite CD #3 containing mixed tracks

[XML version](https://www.matroska.org/files/tags/bigbeat-1_3.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag ( *this tag may be omitted as it’s the same as the upper level, but it wouldn’t be coherent with other CDs* )
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of the set in the collection* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1997”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite Mixed by XYZ”
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “3”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “20”
   - Tag
      - Targets ( *the first track of the CD* )
         - ChapterUID = 258369
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Aleem”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Why Hawaii?”
      - SimpleTag
         - TagName = “SUBTITLE”
         - TagString = “Original Formula Mix”
   - Tag
      - Targets
         - ChapterUID = 147258
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Saint Etienne”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Filthy”
      - SimpleTag
         - TagName =  *“SUBTITLE”*
         - TagString = “Monkey Mafia Mix”
      - SimpleTag
         - TagName =  *“REMIXED_BY”*
         - TagString = “Monkey Mafia”
   - Tag
      - Targets
         - ChapterUID = 147258
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “3”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Mo & Skinny”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Wake Up”
   - etc…

### File #4 : Big Beat Elite Repeat CD #1

[XML version](https://www.matroska.org/files/tags/bigbeat-2_1.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString =  *“Big Beat Elite Repeat”*
      - SimpleTag ( *the number of the set in the collection* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1998”
   - Tag
      - Targets
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “10”
   - Tag
      - Targets ( *the first track of the CD* )
         - ChapterUID = 369852
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Jean-Jacques Perrey”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “E.V.A.”
      - SimpleTag
         - TagName = “SUBTITLE”
         - TagString = “Fatboy Slim Remix”
      - SimpleTag
         - TagName = “REMIXED_BY”
         - TagString = “Fatboy Slim”
   - Tag
      - Targets
         - ChapterUID = 741258
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Lo-Fidelity Allstars”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Kool Rok Bass”
   - etc…

### File #5 : Big Beat Elite Repeat CD #2

[XML version](https://www.matroska.org/files/tags/bigbeat-2_2.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString =  *“Big Beat Elite Repeat”*
      - SimpleTag ( *the number of the set in the collection* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1998”
   - Tag
      - Targets
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “10”
   - Tag
      - Targets ( *the first track of the CD* )
         - ChapterUID = 369852
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Rasmus”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Mass Hysteria”
   - Tag
      - Targets
         - ChapterUID = 741258
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Primal Scream”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Burning Wheel”
      - SimpleTag
         - TagName = “SUBTITLE”
         - TagString = “Chemical Brothers Remix”
      - SimpleTag
         - TagName = “REMIXED_BY”
         - TagString = “The Chemical Brothers”
   - etc…

### File #6 : Big Beat Elite Repeat CD #3 mixed

(you can deduce it yourself as an exercise)

### File #7 : Big Beat Elite Complete CD #1

[XML version](https://www.matroska.org/files/tags/bigbeat-3_1.xml)

- Tags
   - Tag
      - Targets ( *tagging the volume information, no target since it covers the whole file* )
         - *TargetTypeValue = 70*
         - *TargetType = “COLLECTION”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Big Beat Elite”
      - SimpleTag ( *the number of CD sets in the collection* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “LABEL”
         - TagString = “Lacerba”
   - Tag
      - Targets ( *tagging the CD information, no target since it covers the whole file* )
         - *TargetTypeValue = 60*
         - *TargetType = “VOLUME”*
      - SimpleTag
         - TagName = “TITLE”
         - TagString =  *“Big Beat Elite Complete”*
      - SimpleTag ( *the number of the set in the collection* )
         - TagName = “PART_NUMBER”
         - TagString =  *“3”*
      - SimpleTag ( *the number of CDs in the set* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “3”
      - SimpleTag
         - TagName = “DATE_RELEASED”
         - TagString = “1998”
   - Tag
      - Targets
         - *TargetTypeValue = 50*
         - *TargetType = “ALBUM”*
      - SimpleTag ( *the number of the CD in the set* )
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag ( *the number of tracks on the CD* )
         - TagName =  *“TOTAL_PARTS”*
         - TagString = “10”
   - Tag
      - Targets ( *the first track of the CD* )
         - ChapterUID = 369852
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “1”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “The Herbaliser”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Wall Crawling Giant Insect Breaks”
   - Tag
      - Targets
         - ChapterUID = 741258
         - *TargetTypeValue = 30*
         - *TargetType = “TRACK”*
      - SimpleTag
         - TagName =  *“PART_NUMBER”*
         - TagString = “2”
      - SimpleTag
         - TagName = “ARTIST”
         - TagString = “Psychedelia Smith”
      - SimpleTag
         - TagName = “TITLE”
         - TagString = “Different Strokes”
   - etc…

### File #8 : Big Beat Elite Complete CD #2

(you can deduce it yourself as an exercise)

### File #9 : Big Beat Elite Complete CD #3 mixed

(you can deduce it yourself as an exercise)
