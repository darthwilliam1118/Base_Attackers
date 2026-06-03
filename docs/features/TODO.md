# TODO list for Base Attackers
## Small tweaks to be implemented after all major phases are completed
## Game Play Tweaks:
### Boss:
1. [DONE] Boss should move up/down oscillate on levels where there is room for that (terrain to terrain or terrain to top of window)
2. [DONE]Tweak origins of boss bullets to match gun locations on sprite. 
3. Boss explosions when hit by player
4. [DONE] Boss guns at 19,70 and 19,172 from top left of sprite boss_gun.png
5. [DONE] Boss bullets must live longer and go off screen before disappearing.
6. [DONE] Align boss bullets origin with gun locations
7. Boss blinks into view, it should spawn before any of it is visible. probably due to boss scale factor
8. [DONE} do we still want boss hardpoints as separate sprites? yes now they work
9. check boss collision detection - we want tight as possible since it has weird shape
10. Future: This should be implemented "per boss" for future ability to have different PNG for different bosses (with different gun positions, lasers, etc)
### Game General:
1. Fuel only consumed when a thrust key is pressed4. As the tunnel gets smaller, we are really increasing the bottom terrain but the bottom and top terrain should increase equally (so the tunnel is mostly in the middle of the window, currently biased towards the top)
2. Can we have higher levels take more advantage of the scrolling up/down (tunnel gets even more wavy)
3. Different levels can use different colors or textures for terrain or tiles - got to find these assets
4. When docking, instead of instantaneously docking, ship should enter a "docking" mode where it travels at a steady rate to the docking point. Player can interrupt docking by pressing spacebar to release it, just like when docked. When "docking" state completes, ship goes to "docked" state. Improves gameplay look.
5. on higher levels, terrain builds up more from the bottom than the top, so the tunnel is not centered in the window. adjust so it stays more in the center.
6. improve radar "dots" and color choices.
7. Game config menu - lives, music vol, effect vol
8. Move font stuff and assets to agf - all games will use the same fonts
### Flying Enemies:
1. Kamakazi enemies are not centered on the player, and also should "give up" if player avoids them, right now they circle back in and you can't do anything
### Player:
1. Player needs a "bomb" to attack ground targets.
### Power ups:
1. Need to change power up graphics (blue pill for fuel, red pill for health) check the others.
2. Smart bullets might be a good powerup. When active, player bullets automagically target the nearest enemy (ship or gun or laser)
3. For rapid fire powerup, continuous press of spacebar should cause rapid 0.05s bullet firing, until it times out

