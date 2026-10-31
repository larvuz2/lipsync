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

## For a Hungarian speaker to spot-check

The Hungarian audio is hard to transcribe in these places, so the English is a best guess:

| Clip | English now |
|---|---|
| 104461 (0–4.7 s) | Only the queen. The king, as usual, is running late. |
| 104123 | And I gave it to your father-in-law. |
| 104695 (3.8–7.3 s) | If you don't come back, the king won't come back to this house. |
| 107827 | I need you to live with me. / Help me with everything. / I won't let you down. |
| 91750 | Let go of me! |

If the client has the Hungarian script or subtitles, sending them would let us confirm these lines.
