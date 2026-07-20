> **Source:** https://www.matroska.org/technical/tagging.html
> Automated Markdown transcription of the official Matroska / MKVToolNix technical documentation, structured for AI-agent consumption. Original copyright of the respective authors / Matroska organization applies.

---

# Tagging

When a Tag is nested within another Tag, the nested Tag becomes an attribute of the base tag. For instance, if you wanted to store the dates that a singer used certain addresses for, that singer being the lead singer for a track that included multiple bands simultaneously, then your tag tree would look something like this:

- Targets
   - TrackUID
- BAND
   - LEADPERFORMER
      - ADDRESS
         - DATE
         - DATEEND
      - ADDRESS
         - DATE

In this way, it becomes possible to store any Tag as attributes of another tag.

Multiple items **SHOULD** never be stored as a list in a single TagString. If there is more than one tag of a certain type to be stored, then more than one SimpleTag **SHOULD** be used.

## Why official tags matter

There is a debate between people who think all tags **SHOULD** be free and those who think all tags **SHOULD** be strict. If you look at this page you will realize we are in between.

Advanced-users application might let you put any tag in your file. But for the rest of the applications, they usually give you a basic list of tags you can use. Both have their needs. But it’s usually a bad idea to use custom/exotic tags because you will probably be the only person to use this information even though everyone else could benefit from it. So hopefully, when someone wants to put information in one’s file, they will find an official one that fit them and hopefully use it ! If it’s not in the list, this person can contact us any time for addition of such a missing tag. But it doesn’t mean it will be accepted… Matroska files are not meant the become a whole database of people who made costumes for a film. A website would be better for that… It’s hard to define what **SHOULD** be in and what doesn’t make sense in a file. So we’ll treat each request carefully.

We also need an official list simply for developers to be able to display relevant information in their own design (if they choose to support a list of meta-information they **SHOULD** know which tag has the wanted meaning so that other apps could understand the same meaning).

## Tag Formatting

- The TagName  **SHOULD**  consists of capital letters, numbers and the underscore character ‘_’.
- The TagName  **SHOULD NOT**  contain any space.
- TagNames starting with the underscore character ‘_’ are not official tags; see (#why-official-tags-matter).
- The fields with dates  **SHOULD**  have the following format: YYYY-MM-DD hh:mm:ss.mss YYYY = Year, MM = Month, DD = Days, HH = Hours, mm = Minutes, ss = Seconds, mss = Milliseconds. To store less accuracy, you remove items starting from the right. To store only the year, you would use, “2004”. To store a specific day such as May 1st, 2003, you would use “2003-05-01”.
- Fields that require a Float  **SHOULD**  use the “.” mark instead of the “,” mark. To display it differently for another local, applications  **SHOULD**  support auto replacement on display. Also, a thousandths separator  **SHOULD NOT**  be used.
- For currency amounts, there  **SHOULD**  only be a numeric value in the Tag. Only numbers, no letters or symbols other than “.”. For instance, you would store “15.59” instead of “$15.59USD”.

## Target types

The TargetType element allows tagging of different parts that are inside or outside a given file. For example, in an audio file with one song you could have information about the album it comes from and even the CD set even if it’s not found in the file.

For application to know what kind of information (like TITLE) relates to a certain level (CD title or track title), we also need a set of official TargetType names. For now audio and video will have different values & names. That also means the same tag name can have different meanings depending on where it is (otherwise we would end up with 15 TITLE_ tags).

| TargetTypeValue | Audio strings | Video strings | Comment |
| --- | --- | --- | --- |
| 70 | COLLECTION | COLLECTION | the high hierarchy consisting of many different lower items |
| 60 | EDITION / ISSUE / VOLUME / OPUS | SEASON / SEQUEL / VOLUME | a list of lower levels grouped together |
| 50 | ALBUM / OPERA / CONCERT | MOVIE / EPISODE / CONCERT | the most common grouping level of music and video (equals to an episode for TV series) |
| 40 | PART / SESSION | PART / SESSION | when an album or episode has different logical parts |
| 30 | TRACK / SONG | CHAPTER | the common parts of an album or a movie |
| 20 | SUBTRACK / PART / MOVEMENT | SCENE | corresponds to parts of a track for audio (like a movement) |
| 10 | - | SHOT | the lowest hierarchy found in music or movies |

Table: TargetTypeValue values semantic description

An upper level value tag applies to the lower level. That means if a CD has the same artist for all tracks, you just need to set the ARTIST tag at level 50 (ALBUM) and not to each TRACK (but you can). That also means that, if some parts of the CD have no known ARTIST, the value **MUST** be set to nothing (a void string “”).

When a level doesn’t exist it **MUST NOT** be specified in the files, so that the TOTAL_PARTS and PART_NUMBER elements match the same levels.

Here is an example of how these `organizational` tags work: If you set 10 TOTAL_PARTS to the ALBUM level (40) it means the album contains 10 lower parts. The lower part in question is the first lower level that is specified in the file. So, if it’s TRACK (30), then that means it contains 10 tracks. If it’s MOVEMENT (20), that means it’s 10 movements, etc.

## Official tags

The following is a complete list of the supported Matroska Tags. While it is possible to use Tag names that are not listed below, this is not recommended as compatibility will be compromised. If you find that there is a Tag missing that you would like to use, then please contact the Matroska team for its inclusion in the specifications before the format reaches 1.0.

## Nesting Information

Nesting Information tags are intended to contain other tags.

| Tag Name | Type | Description |
| --- | --- | --- |
| ORIGINAL | - | A special tag that is meant to have other tags inside (using nested tags) to describe the original work of art that this item is based on. All tags in this list can be used “under” the ORIGINAL tag like LYRICIST, PERFORMER, etc. |
| SAMPLE | - | A tag that contains other tags to describe a sample used in the targeted item taken from another work of art. All tags in this list can be used “under” the SAMPLE tag like TITLE, ARTIST, DATE_RELEASED, etc. |
| COUNTRY | UTF-8 | The name of the country that is meant to have other tags inside (using nested tags) to country specific information about the item, in the Matroska countries form, i.e. [@!BCP47] two-letter region subtag, without the UK exception. All tags in this list can be used “under” the COUNTRY_SPECIFIC tag like LABEL, PUBLISH_RATING, etc. |

Table: Nesting Information tags

## Organization Information

| Tag Name | Type | Description |
| --- | --- | --- |
| TOTAL_PARTS | UTF-8 | Total number of parts defined at the first lower level. (e.g., if TargetType is ALBUM, the total number of tracks of an audio CD) |
| PART_NUMBER | UTF-8 | Number of the current part of the current level. (e.g., if TargetType is TRACK, the track number of an audio CD) |
| PART_OFFSET | UTF-8 | A number to add to PART_NUMBER, when the parts at that level don’t start at 1. (e.g., if TargetType is TRACK, the track number of the second audio CD) |

Table: Organization Information tags

## Titles

| Tag Name | Type | Description |
| --- | --- | --- |
| TITLE | UTF-8 | The title of this item. For example, for music you might label this “Canon in D”, or for video’s audio track you might use “English 5.1” This is akin to the “TIT2” tag in [@!ID3v2]. |
| SUBTITLE | UTF-8 | Sub Title of the entity. |

Table: Titles tags

## Nested Information

Nested Information includes tags contained in other tags.

| Tag Name | Type | Description |
| --- | --- | --- |
| URL | UTF-8 | URL corresponding to the tag it’s included in. |
| SORT_WITH | UTF-8 | A child element to indicate what alternative value the parent tag can have to be sorted – for example, “Pet Shop Boys” instead of “The Pet Shop Boys”. Or “Marley Bob” and “Marley Ziggy” (no comma needed). |
| INSTRUMENTS | UTF-8 | The instruments that are being used/played, separated by a comma. It **SHOULD** be a child of the following tags: ARTIST, LEAD_PERFORMER, or ACCOMPANIMENT. |
| EMAIL | UTF-8 | Email corresponding to the tag it’s included in. |
| ADDRESS | UTF-8 | The physical address of the entity. The address **SHOULD** include a country code. It can be useful for a recording label. |
| FAX | UTF-8 | The fax number corresponding to the tag it’s included in. It can be useful for a recording label. |
| PHONE | UTF-8 | The phone number corresponding to the tag it’s included in. It can be useful for a recording label. |

Table: Nested Information tags

## Entities

| Tag Name | Type | Description |
| --- | --- | --- |
| ARTIST | UTF-8 | A person or band/collective generally considered responsible for the work. This is akin to the “TPE1” tag in [@!ID3v2]. |
| LEAD_PERFORMER | UTF-8 | Lead Performer/Soloist(s). This can sometimes be the same as ARTIST. |
| ACCOMPANIMENT | UTF-8 | Band/orchestra/accompaniment/musician. This is akin to the “TPE2” tag in [@!ID3v2]. |
| COMPOSER | UTF-8 | The name of the composer of this item. This is akin to the “TCOM” tag in [@!ID3v2]. |
| ARRANGER | UTF-8 | The person who arranged the piece, e.g., Ravel. |
| LYRICS | UTF-8 | The lyrics corresponding to a song (in case audio synchronization is not known or as a doublon to a subtitle track). Editing this value, when subtitles are found, **SHOULD** also result in editing the subtitle track for more consistency. |
| LYRICIST | UTF-8 | The person who wrote the lyrics for a musical item. This is akin to the “TEXT” tag in [@!ID3v2]. |
| CONDUCTOR | UTF-8 | Conductor/performer refinement. This is akin to the “TPE3” tag in [@!ID3v2]. |
| DIRECTOR | UTF-8 | This is akin to the “IART” tag [@?RIFF.tags]. |
| ASSISTANT_DIRECTOR | UTF-8 | The name of the assistant director. |
| DIRECTOR_OF_PHOTOGRAPHY | UTF-8 | The name of the director of photography, also known as cinematographer. This is akin to the “ICNM” tag in [@?RIFF.tags]. |
| SOUND_ENGINEER | UTF-8 | The name of the sound engineer or sound recordist. |
| ART_DIRECTOR | UTF-8 | The person who oversees the artists and craftspeople who build the sets. |
| PRODUCTION_DESIGNER | UTF-8 | Artist responsible for designing the overall visual appearance of a movie. |
| CHOREGRAPHER | UTF-8 | The name of the choregrapher |
| COSTUME_DESIGNER | UTF-8 | The name of the costume designer |
| ACTOR | UTF-8 | An actor or actress playing a role in this movie. This is the person’s real name, not the character’s name the person is playing. |
| CHARACTER | UTF-8 | The name of the character an actor or actress plays in this movie. This **SHOULD** be a sub-tag of an `ACTOR` tag in order not to cause ambiguities. |
| WRITTEN_BY | UTF-8 | The author of the story or script (used for movies and TV shows). |
| SCREENPLAY_BY | UTF-8 | The author of the screenplay or scenario (used for movies and TV shows). |
| EDITED_BY | UTF-8 | This is akin to the “IEDT” tag in [@?RIFF.tags]. |
| PRODUCER | UTF-8 | Produced by. This is akin to the “IPRO” tag in [@?RIFF.tags]. |
| COPRODUCER | UTF-8 | The name of a co-producer. |
| EXECUTIVE_PRODUCER | UTF-8 | The name of an executive producer. |
| DISTRIBUTED_BY | UTF-8 | This is akin to the “IDST” tag in [@?RIFF.tags]. |
| MASTERED_BY | UTF-8 | The engineer who mastered the content for a physical medium or for digital distribution. |
| ENCODED_BY | UTF-8 | This is akin to the “TENC” tag in [@!ID3v2]. |
| MIXED_BY | UTF-8 | DJ mix by the artist specified |
| REMIXED_BY | UTF-8 | Interpreted, remixed, or otherwise modified by. This is akin to the “TPE4” tag in [@!ID3v2]. |
| PRODUCTION_STUDIO | UTF-8 | This is akin to the “ISTD” tag in [@?RIFF.tags]. |
| THANKS_TO | UTF-8 | A very general tag for everyone else that wants to be listed. |
| PUBLISHER | UTF-8 | This is akin to the “TPUB” tag in [@!ID3v2]. |
| LABEL | UTF-8 | The record label or imprint on the disc. |

Table: Entities tags

## Search and Classification

| Tag Name | Type | Description |
| --- | --- | --- |
| GENRE | UTF-8 | The main genre (classical, ambient-house, synthpop, sci-fi, drama, etc.). The format follows the infamous “TCON” tag in [@!ID3v2]. |
| MOOD | UTF-8 | Intended to reflect the mood of the item with a few keywords, e.g., “Romantic”, “Sad” or “Uplifting”. The format follows that of the “TMOO” tag in [@!ID3v2]. |
| ORIGINAL_MEDIA_TYPE | UTF-8 | Describes the original type of the media, such as, “DVD”, “CD”, “computer image,” “drawing,” “lithograph,” and so forth. This is akin to the “TMED” tag in [@!ID3v2]. |
| CONTENT_TYPE | UTF-8 | The type of the item. e.g., Documentary, Feature Film, Cartoon, Music Video, Music, Sound FX, … |
| SUBJECT | UTF-8 | Describes the topic of the file, such as “Aerial view of Seattle.” |
| DESCRIPTION | UTF-8 | A short description of the content, such as “Two birds flying.” |
| KEYWORDS | UTF-8 | Keywords to the item separated by a comma, used for searching. |
| SUMMARY | UTF-8 | A plot outline or a summary of the story. |
| SYNOPSIS | UTF-8 | A description of the story line of the item. |
| INITIAL_KEY | UTF-8 | The initial key that a musical track starts in. The format is identical to “TKEY” tag in [@!ID3v2]. |
| PERIOD | UTF-8 | Describes the period that the piece is from or about. For example, “Renaissance”. |
| LAW_RATING | UTF-8 | Depending on the `COUNTRY` it’s the format of the rating of a movie (P, R, X in the USA, an age in other countries or a URI defining a logo). |

Table: Search and Classification tags

## Temporal Information

| Tag Name | Type | Description |
| --- | --- | --- |
| DATE_RELEASED | UTF-8 | The time that the item was originally released. This is akin to the “TDRL” tag in [@!ID3v2]. |
| DATE_RECORDED | UTF-8 | The time that the recording began. This is akin to the “TDRC” tag in [@!ID3v2]. |
| DATE_ENCODED | UTF-8 | The time that the encoding of this item was completed began. This is akin to the “TDEN” tag in [@!ID3v2]. |
| DATE_TAGGED | UTF-8 | The time that the tags were done for this item. This is akin to the “TDTG” tag in [@!ID3v2]. |
| DATE_DIGITIZED | UTF-8 | The time that the item was transferred to a digital medium. This is akin to the “IDIT” tag in [@?RIFF.tags]. |
| DATE_WRITTEN | UTF-8 | The time that the writing of the music/script began. |
| DATE_PURCHASED | UTF-8 | Information on when the file was purchased; see also (#commercial) on purchase tags. |

Table: Temporal Information tags

## Spatial Information

| Tag Name | Type | Description |
| --- | --- | --- |
| RECORDING_LOCATION | UTF-8 | The location where the item was recorded, in the Matroska countries form, i.e. [@!BCP47] two-letter region subtag, without the UK exception. This code is followed by a comma, then more detailed information such as state/province, another comma, and then city. For example, “US, Texas, Austin”. This will allow for easy sorting. It is okay to only store the country, or the country and the state/province. More detailed information can be added after the city through the use of additional commas. In cases where the province/state is unknown, but you want to store the city, simply leave a space between the two commas. For example, “US, , Austin”. |
| COMPOSITION_LOCATION | UTF-8 | Location that the item was originally designed/written, in the Matroska countries form, i.e. [@!BCP47] two-letter region subtag, without the UK exception. This code is followed by a comma, then more detailed information such as state/province, another comma, and then city. For example, “US, Texas, Austin”. This will allow for easy sorting. It is okay to only store the country, or the country and the state/province. More detailed information can be added after the city through the use of additional commas. In cases where the province/state is unknown, but you want to store the city, simply leave a space between the two commas. For example, “US, , Austin”. |
| COMPOSER_NATIONALITY | UTF-8 | Nationality of the main composer of the item, mostly for classical music, in the Matroska countries form, i.e. [@!BCP47] two-letter region subtag, without the UK exception. |

Table: Spatial Information tags

## Personal

| Tag Name | Type | Description |
| --- | --- | --- |
| COMMENT | UTF-8 | Any comment related to the content. |
| PLAY_COUNTER | UTF-8 | The number of time the item has been played. |
| RATING | UTF-8 | A numeric value defining how much a person likes the song/movie. The number is between 0 and 5 with decimal values possible (e.g., 2.7), 5(.0) being the highest possible rating. Other rating systems with different ranges will have to be scaled. |

Table: Personal tags

## Technical Information

| Tag Name | Type | Description |
| --- | --- | --- |
| ENCODER | UTF-8 | The software or hardware used to encode this item. (“LAME” or “XviD”) |
| ENCODER_SETTINGS | UTF-8 | A list of the settings used for encoding this item. No specific format. |
| BPS | UTF-8 | The average bits per second of the specified item. This is only the data in the Blocks, and excludes headers and any container overhead. |
| FPS | UTF-8 | The average frames per second of the specified item. This is typically the average number of Blocks per second. In the event that lacing is used, each laced chunk is to be counted as a separate frame. |
| BPM | UTF-8 | Average number of beats per minute in the complete target (e.g., a chapter). Usually a decimal number. |
| MEASURE | UTF-8 | In music, a measure is a unit of time in Western music like “4/4”. It represents a regular grouping of beats, a meter, as indicated in musical notation by the time signature. The majority of the contemporary rock and pop music you hear on the radio these days is written in the 4/4 time signature. |
| TUNING | UTF-8 | It is saved as a frequency in hertz to allow near-perfect tuning of instruments to the same tone as the musical piece (e.g., “441.34” in Hertz). The default value is 440.0 Hz. |
| REPLAYGAIN_GAIN | binary | The gain to apply to reach 89dB SPL on playback. This is based on the [@!ReplayGain] standard. Note that ReplayGain information can be found at all TargetType levels (track, album, etc). |
| REPLAYGAIN_PEAK | binary | The maximum absolute peak value of the item. This is based on the [@!ReplayGain] standard. |

Table: Technical Information tags

## Identifiers

| Tag Name | Type | Description |
| --- | --- | --- |
| ISRC | UTF-8 | The International Standard Recording Code [@!ISRC], excluding the “ISRC” prefix and including hyphens. |
| MCDI | binary | This is a binary dump of the TOC of the CDROM that this item was taken from. This holds the same information as the “MCDI” in [@!ID3v2]. |
| ISBN | UTF-8 | International Standard Book Number [@!ISBN]. |
| BARCODE | UTF-8 | European Article Numbering EAN-13 barcode defined in [@!GS1] General Specifications. |
| CATALOG_NUMBER | UTF-8 | A label-specific string used to identify the release – for example, TIC 01. |
| LABEL_CODE | UTF-8 | A 4-digit or 5-digit number to identify the record label, typically printed as (LC) xxxx or (LC) 0xxxx on CDs medias or covers (only the number is stored). |
| LCCN | UTF-8 | Library of Congress Control Number [@!LCCN]. |
| IMDB | UTF-8 | Internet Movie Database [@!IMDb] identifier. “tt” followed by at least 7 digits for Movies, TV Shows, and Episodes. |
| TMDB | UTF-8 | The Movie DB “movie_id” or “tv_id” identifier for movies/TV shows [@!MovieDB]. The variable length digits string **MUST** be prefixed with either “movie/” or “tv/”. |
| TVDB | UTF-8 | The TV Database “Series ID” or “Episode ID” identifier for TV shows [@!TheTVDB]. Variable length all-digits string identifying a TV Show. |
| TVDB2 | UTF-8 | The TV Database [@!TheTVDB] tag which can include movies. The variable length digits string representing a “Series ID”, “Episode ID” or “Movie ID” identifier **MUST** be prefixed with “series/”, “episodes/” or “movies/” respectively. |

Table: Identifiers tags

## Commercial

| Tag Name | Type | Description |
| --- | --- | --- |
| PURCHASE_ITEM | UTF-8 | URL to purchase this file. This is akin to the “WPAY” tag in [@!ID3v2]. |
| PURCHASE_INFO | UTF-8 | Information on where to purchase this album. This is akin to the “WCOM” tag in [@!ID3v2]. |
| PURCHASE_OWNER | UTF-8 | Information on the person who purchased the file. This is akin to the “TOWN” tag in [@!ID3v2]. |
| PURCHASE_PRICE | UTF-8 | The amount paid for entity. There **SHOULD** only be a numeric value in here. Only numbers, no letters or symbols other than “.”. For instance, you would store “15.59” instead of “$15.59USD”. |
| PURCHASE_CURRENCY | UTF-8 | The currency type used to pay for the entity. Use [@!ISO4217] for the 3 letter alphabetic code. |

Table: Commercial tags

## Legal

| Tag Name | Type | Description |
| --- | --- | --- |
| COPYRIGHT | UTF-8 | The copyright information as per the copyright holder. This is akin to the “TCOP” tag in [@!ID3v2]. |
| PRODUCTION_COPYRIGHT | UTF-8 | The copyright information as per the production copyright holder. This is akin to the “TPRO” tag in [@!ID3v2]. |
| LICENSE | UTF-8 | The license applied to the content (like Creative Commons variants). |
| TERMS_OF_USE | UTF-8 | The terms of use for this item. This is akin to the “USER” tag in [@!ID3v2]. |

Table: Legal tags

## Notes

- In the Target list, a logical OR is applied on all tracks, a logical OR is applied on all chapters. Then a logical AND is applied between the Tracks list and the Chapters list to know if an element belongs to this Target.
