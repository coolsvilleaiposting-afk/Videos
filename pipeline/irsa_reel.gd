extends Node
## Coolsville Crossings footage reel for Shards of Irsa (spoiler-free: ordinary fights and walking only,
## no bosses, no story scenes). Copied into the game's tests/ folder at render time by irsa_footage.sh:
##   godot --write-movie out.avi --fixed-fps 30 --resolution 1440x1056 -- level=village stage=27 skip
##         testnode=res://tests/zz_social_reel.gd [seg=0]
## seg picks one segment (0..4) so each render stays short; no seg plays them all.

var w: World
const FIGHT_SPEED := 1.5

const SEGMENTS := [
	{"entry": "woods_s", "arena": "forest", "lv": 12, "job": "/datum/job/sorcerer",
		"foes": ["/mob/enemy/goblin", "/mob/enemy/goblin", "/mob/enemy/wolf"], "title": "Goblins"},
	{"entry": "frost_w", "arena": "frost", "lv": 28, "job": "/datum/job/knight",
		"foes": ["/mob/enemy/frostwolf", "/mob/enemy/yeti", "/mob/enemy/frostwolf"], "title": "Frosthollow"},
	{"entry": "coast_n", "arena": "coast", "lv": 30, "job": "/datum/job/monk",
		"foes": ["/mob/enemy/crab", "/mob/enemy/drowned", "/mob/enemy/crab"], "title": "The Shore"},
	{"entry": "barrens_n", "arena": "barrens", "lv": 22, "job": "/datum/job/rogue",
		"foes": ["/mob/enemy/scorpion", "/mob/enemy/raider", "/mob/enemy/scorpion"], "title": "The Barrens"},
	{"entry": "dungeon_s", "arena": "dungeon", "lv": 12, "job": "/datum/job/cleric",
		"foes": ["/mob/enemy/skeleton", "/mob/enemy/skeleton", "/mob/enemy/skeleton"], "title": "Skeletons"},
]


func _wait(t: float) -> void:
	await get_tree().create_timer(t).timeout


func _party(lv: int, job: String) -> void:
	PC.new_hero("Sporkeh", job, "m", 0)
	PC.flags.erase("new")
	PC.allies.clear()
	while PC.hero.level < lv:
		PC.hero.level_up()
	PC.hero.auto_spend_talents()
	PC.ally_join("idris", lv)
	PC.ally_join("sera", lv)
	for m in PC.party():
		# best regular gear each member can wear, so ordinary fights end in a win
		for slot in Gear.SLOTS:
			var best := ""
			var score := -1.0
			for p in Gear.all_gear_paths():
				if str(p).begins_with("/datum/gear/unique"):
					continue
				var g := Gear.get_gear(p)
				if g.slot != slot or not g.can_equip(m):
					continue
				if g.tier * 1000.0 + g.price > score:
					score = g.tier * 1000.0 + g.price
					best = p
			if best == "":
				continue
			var old := m.equipped_in(slot)
			if old != "":
				m.apply_gear(old, -1)
			m.equipment[slot] = best
			m.apply_gear(best, 1)
		m.hp = m.max_hp
		m.mp = m.max_mp
	PC.add_item("/datum/item/hi_potion", 6)
	PC.charm_given = true
	PC.quest_min = true
	w.place_followers()


func _walk(secs: float) -> void:
	# wander along open ground so the overworld gets some screen time
	var dirs := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]
	var d := 0
	var t := 0.0
	w.hud.show_explore(false)	# no quest text (spoilers) or menus over the scenery
	while t < secs:
		w.hud.show_explore(false)
		if not w.player.moving:
			var tries := 0
			while w.zone.is_blocked(w.player.cell + dirs[d]) and tries < 4:
				d = (d + 1) % 4
				tries += 1
			if tries < 4:
				w.player._step_to(w.player.cell + dirs[d])
			if randf() < 0.15:
				d = (d + 1 + randi() % 2) % 4
		await _wait(0.1)
		t += 0.1


func _segment(s: Dictionary) -> void:
	_party(int(s.lv), str(s.job))
	w.travel(str(s.entry))
	await _wait(1.5)
	for k in w.zone.wilds.duplicate():
		k.queue_free()
	w.zone.wilds.clear()
	await _walk(6.0)
	var foes: Array[Fighter] = []
	for p in s.foes:
		foes.append(Fighter.monster(p))
	Engine.time_scale = FIGHT_SPEED
	var outcome: String = await w.start_battle(foes, str(s.arena), str(s.title), {"no_escape": true})
	Engine.time_scale = 1.0
	print("REEL ", s.title, " ", outcome)
	await _wait(2.5)
	await _walk(4.0)


func _ready() -> void:
	Game.auto_advance = true
	Game.hour_override = 12.0
	Battle.auto_hero = true
	randomize()
	await _wait(1.0)
	w = get_parent().world
	var only := -1
	for a in OS.get_cmdline_user_args():
		if a.begins_with("seg="):
			only = int(a.substr(4))
	for i in SEGMENTS.size():
		if only >= 0 and i != only:
			continue
		await _segment(SEGMENTS[i])
	print("REEL done")
	get_tree().quit()
