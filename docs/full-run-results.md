# Full run: Rise of the Raven S01E01 in English (58 clips)

Same process as the test winner: **Sync auto-dub** (Hungarian to American English, each actor's voice
cloned automatically) + **sync-3** lip sync on every shot where the speaker's face is visible.
Deliverables are the 58 final `.mp4` files only, with the original file names. Their numbering keeps
the original order.

## What each clip got

- **39 clips lip-synced** (53 sync-3 jobs): every on-camera speaking shot, pinned to the speaker's face.
  - Two people talking in one shot (102229, 106229, 109943): two chained jobs, each fed only its own
    speaker's English, so the listener's mouth stays still.
  - 87434 and 87646 reuse the approved test versions (87646 = test 87646 + 87725, frame-exact).
- **19 clips English audio only**: the speaker is off-screen, or it's a scream or name shout, so the
  picture is untouched.
- Frames outside the lip-synced shots are the original frames (frame-exact rebuild, checked: every
  output has exactly the source's frame count).

## Checks done

- **Characters:** the speaker of every line was identified from the picture (face detection and mouth
  movement) and from the voice (pitch per sentence). Each lip-sync pin was checked to sit on that
  person's face on its frame. Every finished lip-sync job was checked: the change sits on the pinned
  face, and the mouth crops were reviewed by eye.
- **Words:** every English track was transcribed back with Whisper and compared with the Hungarian. The
  auto-dub got names and a few lines wrong; those were fixed (below) and the fixed tracks re-checked.
- **First clip (87434):** the same male character as in the test (the trainer). His English voice
  matches the actor's own voice better than any other version (speaker-ID 0.61). He calls the line
  out a little higher than the actor's calm delivery.

## Translation fixes (on top of the auto-dub)

Fixed lines use clones of each character's own dub voice, made from that character's lines in the dub.
The clones are FATHER, ERZSEBET, HUNYADI, OLDNOBLE, DARKWOMAN and MIKLOS. Fixed lines play at natural
pace (0.93–1.12x).

| Clip | Auto-dub said | Now |
|---|---|---|
| 90527 | Bring me my *partridge* … | Bring me my **bracer** … (one word replaced) |
| 101676 | *I was going to* kill it. | **I let you** kill it. |
| 102229 | You're *Miho's* sister | You're **Mihai's** sister (Mihály) |
| 103629 | Though in truth, it was inspired by my love for you. | But in truth, it belongs to you, my love. |
| 103835 | I'm coming. | Come on! |
| 104240 | How do you look like? / Come on, get dressed. The king is coming, your Hungarian. / Is Zygismund already here? | Look at the state of you! / Come on, let's go! / The King of Hungary is here! / Is Sigismund here already? |
| 104461 | Only the queen. King Kasnik usually plays with his cow. / Wait. / Excuse me, Janko. | Only the queen. The king, as usual, is running late. / Father! / Thank you, my dear. Jankó! |
| 104695 | (line missing) | It'll be fine. |
| 105002 | will be want you | You'll behave, won't you? |
| 105386 | *Herjibet* Szilagyi is my betrothed. | **Erzhebet** Szilagyi … |
| 108806 | … as jealous as *we lucky*. | … as jealous as **Újlaki**. |

The original actor's own audio was kept for name shouts and screams where the dub had garbled them.
These are in 91606, 92071, 92290, 95210, 103835 ("Hé, Jankó!") and 109692. Stray dub words were muted
in 91928, 104461, 105583 and 106957.

## Serbian scenes (language check)

A language check of every final phrase found no Hungarian dialogue left (character names only).
It did find that the scenes with the Serbian lord Branković's family are in **Serbian** in the
original. The auto-dub (set to Hungarian -> English) had left 4 of them in Serbian (103835, 104123,
104695, 107827), and 109692 still had the original shout "Gospodaru!". These lines were transcribed
in Serbian, translated, and re-voiced in the characters' cloned voices, then re-lip-synced:

| Clip | Serbian | English now |
|---|---|---|
| 103835 | Taj vuk pripada meni, jer si ga ubio na srpskoj zemlji. | That wolf belongs to me. You killed it on Serbian soil. |
| 104123 | Ali sam ga dao tvojoj kćeri. | But I gave it to your daughter. |
| 104240 | Ajde, umij se, obuci se. Kralj dolazi, tvoj, mađarski. | Wash up, get dressed! / The king is coming. Your Hungarian king. |
| 104461 | Samo kraljica. Kralj kasni kao obično, sigurno se još zabavlja sa svojim kurvama. / Oprosti, kćeri. Janko! | Only the queen. The king is late, as usual. No doubt still amusing himself with his whores. / Excuse me, daughter. Janko! |
| 104695 | Slušaj, ovo veče je za mene jako važno. / Ako razljutiš kralja, u ovu kuću više ne dolaziš. / Zato pazi što radiš. | Listen, this evening is very important to me. / If you anger the king, don't you ever come back to this house. / So watch what you do. |
| 107827 | Mara mi je potrebna da živi uz mene, pomaže mi u svemu, ne mogu je dati na tvoj dvor. | I need Mara here with me. She helps me with everything. I can't give her to your court. |
| 109692 | Gospodaru! | My lord! (minor character; voiced with the FATHER clone) |

## For a Hungarian speaker to spot-check

The Hungarian audio is hard to transcribe in these places, so the English is a best guess:

| Clip | English now |
|---|---|
| 91750 | Let go of me! |

If the client has the Hungarian script or subtitles, sending them would let us confirm these lines.

## Client review round (final revision)

| Clip | Note from review | Fix |
|---|---|---|
| 108382, 102229, 102065 | Glitch / no continuity in the mouth | These are single continuous shots and the lip sync started and ended mid-shot, so the lower face jumped at those frames. Lip sync now covers the full shot (108382: until Erzsébet turns away, and it now includes her "You again?"). |
| 104240 | Wrong voice (should be male) | "Look at the state of you! / Wash up, get dressed!" are Branković's lines; re-voiced in his voice. |
| 105002 | Static mouth / wrong speaker | The line "You'll behave, won't you?" is said off camera by Branković's daughter (client; voice match 0.35, female ~200 Hz). Re-voiced in her voice; no lip sync, picture untouched. |

## Client review round 3

The clips the client sent for this round are byte-identical to our source clips, so the same timings and voices apply.

| Clip | Note from review | Fix |
|---|---|---|
| 108943 | She is off with "I think so too" | Her line was not lip-synced. It now is, while she faces the camera. |
| 105832 | "Not yet… your Majesty" sync is off | These lines were wrongly treated as an off-screen man. They are hers (female voice) and are now lip-synced on her close-up together with "I am not your wife, Miklós". |
| 104240 | The King is all off with sync | The English came 0.4–0.5 s early. The lines are now timed to the original Serbian, and the close-ups are re-lip-synced. "Is Sigismund here already?" now uses the new Hunyadi voice. |
| 104123 | Not manly enough (he just killed a wolf) | The old clone was made from the dub. There is now a new Hunyadi voice (HUNYADI2), cloned from the actor's own lines and set to the dub Hunyadi's pitch (~100 Hz). Re-lip-synced. |
| 102229 | High-pitch drop-out on the man; pixel jump by her face | The swapped name came from a thin clone at about 150 Hz in a ~100 Hz line. It is now "Mihai's sister", taken from the new Hunyadi voice and pitch-matched to the dub's own pitch on those words (heard back as "You're Mihaly's sister?"). Each person now has a separate lip-sync pass. |

**Masked, speech-gated composite (all 5 clips):** the final picture is the original frame everywhere except the
speaking person's mouth, chin and jaw. That area comes from face landmarks on both the original and the
lip-synced frame, so it hugs the skin and leaves the hair and background beside the face untouched. It is used
only while that person speaks, following the speech in that person's own lip-sync audio, with short fades that
finish before the first word. Background pixels, and each face while it is not speaking, are the original pixels.

The lip-sync output on its own also changed hair and background bokeh around Erzsébet's face in 102229. That was
the "pixel jump" by her face; the mask now removes it. In 108943 her mouth is hidden by her hand (frames 91–93)
and then by a passing dancer (94–104), so lip sync starts at frame 104 when her face comes back into view.

Checks: no frame-to-frame jumps around any face; 58/58 finals pass (frames, A/V sync, English matches the script).
