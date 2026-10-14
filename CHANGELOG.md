# Changelog

## 0.2.0

- New arms and hands: a sculpted, skin-weighted and textured mesh (based on
  "Rigged Arms" by mrgyarmati, CC-BY-4.0) replaces the procedural one, with
  painted veins, knuckles, palm lines and nails, tinted to every skin tone.
  Fitted to each build's skeleton; the bone names and actions are unchanged.
- Hand proportions re-measured from the new mesh (finger and thumb joints).
- Sleeves take their skin weights from the arm under them, so they bend with
  it; the arm is tucked inside the sleeves and the cloth kept clear of the
  skin, so it never shows through.
- Phone, cup, bottle and flashlight grips refitted to the new hand: the props
  rest against the palm and the fingers wrap them without going inside.
- The thumb's rest pose is compensated in the pose library, so thumb poses
  look as intended with the new hand.
- The wristwatch strap is sized to the wrist it is on.

## 0.1.0

First release.

- POV walks from a Start box to an End box through waypoints, over
  invisible floors: floor planes, stairs, any scene mesh, or a grid dropped
  onto the scene. Live updates and a path, footstep and seconds overlay.
  Footstep markers on the timeline for sound.
- Walking styles: Stroll, Walk, Brisk, Jog, Run, Sneak, Gimbal, Bodycam,
  Wobbly. Bob, sway, roll, acceleration, stairs slowdown and stair rhythm.
- Head motion: look-ahead into turns, neck-pivot turning, slope following,
  watching steps on stairs, handheld wander, breathing; ten look moves
  including Look At Object.
- Procedural arms and hands (three builds, seven skin tones, nine sleeve
  styles, wristwatch) with two-bone IK and finger poses, keyed as plain
  bone rotations.
- Thirteen hand actions with props: cigarette with ember and smoke, phone
  with a lit screen, to-go cup, bottle, flashlight with a spot light.
