# POP PUNK GUITAR ULTIMATE — Pattern Mode Specification

Status: **APPROVED / LOCKED BY USER**
Target: VST3 instrument, Windows x64, FL Studio 20.

## 1. Core behavior

Pattern Mode follows the performance model of Native Instruments Session Guitarist: MIDI keys in a dedicated pattern-selector range select a guitar playing pattern. The instrument then performs that pattern using the chord supplied by the playable MIDI range. Pattern Mode is not a simple WAV loop player and must not pitch-shift an entire recorded loop to fake different chords.

## 2. Approved pattern-selector key map

The following mapping is the approved initial factory layout (key labels must be interpreted using the plugin's documented MIDI octave convention and verified in FL Studio 20):

| Selector key | Pattern |
|---|---|
| C1 | Pop Punk Downstroke |
| C#1 | Palm Mute 8th Notes |
| D1 | Power Chord Rhythm |
| D#1 | Punk Rock Rhythm |
| E1 | Fast Downstroke |
| F1 | Alternative Punk Rhythm |

The layout must be extensible for additional factory patterns and user patterns. Pattern selector keys are control keys; they are not ordinary pitched notes for the guitar part.

## 3. Chord performance

A separate playable MIDI range supplies the chord/root/voicing. When the player changes the chord while a pattern is selected, the engine must render the selected rhythmic performance with the new chord. Examples: select Pop Punk Downstroke, then play C, G, or Am; the rhythmic articulation remains the selected pattern while the harmonic content follows the played chord.

The engine must use reviewed note/chord sample maps, voicings and articulation data. It must not assume that a single full-loop WAV can be transposed to produce every chord.

## 4. Pattern performance requirements

- Downstroke and alternate strumming, including upstroke/downstroke direction where source data supports it.
- Palm-muted and open/normal articulations.
- Power-chord and other reviewed chord voicings.
- Velocity layers and velocity-sensitive attack/dynamics.
- Natural timing and performance variation where supported by recorded material.
- Clean pattern changes: stop or release the previous pattern musically, avoid unintended overlap, clicks and abrupt mid-note cuts.
- Preserve the recorded rhythm and phrase boundaries; do not force quantization or tempo normalization when the source is expressive or irregular.
- Tempo is metadata only when supported by reliable evidence; otherwise mark it unknown/unverified.

## 5. Library Manager responsibilities

Prepare and index the assets needed by this engine:
- reviewed one-shot notes, chord voicings and articulations for Sample Mode;
- reviewed pattern performances and their event/timing data for Pattern Mode;
- separate melodic phrases for Melody Mode.

For every derived candidate preserve source file path, source hash, exact source start/end frame offsets, sample rate, channels, sample format, candidate type, review state and license state. Pattern candidates must also retain their event/onset timing, duration, and tempo with confidence or an explicit unknown value.

The Manager may propose candidates but must never claim that acoustic detection alone proves a guitar note, chord, articulation, musical role, or usable pattern. No automatic promotion to FACTORY.

## 6. MIDI selector and chord-range separation

The VST3 must define and document a non-overlapping pattern-selector range and playable chord range. The approved labels C1–F1 are the initial selector labels; the implementation must verify the actual MIDI note numbers/octave naming in FL Studio 20 and provide a configurable mapping if host octave conventions differ. Selector keys must not accidentally trigger pitched guitar notes.

## 7. Safety and source integrity

Original library files remain read-only during scanning and analysis. No automatic move, rename, overwrite or deletion. Only manually reviewed WAV assets with explicit license approval may be promoted to FACTORY.

## 8. Full-loop recordings and fragment extraction

A complete original recording MAY be used as a Pattern performance when the selected section is already a stable, repeating pattern and can be looped without changing its musical content. Extracting a smaller loop fragment is optional, not mandatory.

A full-loop asset is acceptable when all of the following are verified:
- exact loop start/end sample positions are stored; a full-file loop may use start sample 0 and end sample equal to the file frame count;
- loop end is after loop start and does not exceed the source/derived WAV frame count;
- the loop point transition is verified to be seamless or musically clean, without a click, gap, duplicated attack, or rhythm discontinuity;
- the repeated pattern remains unchanged from cycle to cycle;
- beat grid, tempo/meter (or explicitly unknown values), attack/stroke events, technique/articulation events and harmonic/chord events are retained where supported;
- source path, source SHA-256, exact sample boundaries and derived SHA-256 remain traceable.

Extract a fragment only when a shorter, stable section is materially better for the instrument (for example, the full source contains an intro/fill/break or changing arrangement around the repeated phrase). Never split merely to force a loop where the full recording is already a valid repeating performance.

A Pattern performance WAV is not automatically chromatic. Chord changes must be performed from reviewed pitch-specific note zones, chord voicings and event/timing data; do not pitch-shift one full-band loop to fake arbitrary chords.

## 9. AutoChords and Pattern input when AutoChords is disabled

AutoChords is an expanded PPGU feature, not a copy of the restricted chord choices of a third-party reference instrument.

When AutoChords is ON:
- the user selects a musical key/root and scale;
- the instrument exposes the complete note set belonging to that selected key/scale, not merely a small fixed list of suggested chords;
- scale degrees and the resulting diatonic chord choices must be visible and selectable;
- the selected notes/chords must feed the Pattern chord/event engine and remain synchronized with the user's selected Pattern performance;
- the display must provide musically correct enharmonic spellings where practical (for example, show flats in flat-oriented keys and sharps in sharp-oriented keys).

When AutoChords is OFF:
- Pattern remains fully playable from ordinary MIDI note input across the complete 12-note chromatic set;
- all semitones are available, including C, C#/Db, D, D#/Eb, E, F, F#/Gb, G, G#/Ab, A, A#/Bb and B;
- the UI must not filter, quantize or silently remap incoming notes to the currently selected scale;
- flats/sharps are display spellings for the same MIDI pitches, not additional MIDI notes.

The AutoChords key/scale UI and note/chord list are part of the user-facing performance workflow. Parameters for scale root/mode alone do not count as a completed AutoChords implementation. Completion requires MIDI behavior, visible list generation, correct note/chord output, state recall, and tests.

## 10. Factory grouping and runtime mapping

The Manager must keep the following as separate logical asset groups while allowing one physical WAV/asset to be referenced by more than one engine zone where appropriate:
- Pattern performances: complete original loops or verified extracted loop fragments, preserving loop points, beat grid, timing, tempo/meter, attacks, strokes, articulation and harmonic events;
- Pattern note/chord zones: reviewed pitch-specific single notes, chord voicings and articulations used to render the selected performance against the incoming chord;
- Melody note zones: reviewed pitch-specific notes, key range, velocity range/layers, round-robin group and articulation;
- Melody phrases: separately grouped melodic sequences with confirmed note events and phrase boundaries.

The initial approved Pattern selector labels remain C1-F1 as listed above. Selector key labels must be calibrated against actual MIDI note numbers in the target host. Missing/unknown musical data remains unknown and must be displayed as a gap for review, not fabricated.

