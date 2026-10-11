-- SPDX-License-Identifier: AGPL-3.0-or-later
-- EVAC screen for info-beamer hosted: draws data.json written by the service (see README.md).
-- Priority: evacuation state (full screen, or a top banner for non-takeover states) > announcement takeover >
-- announcement banners > event name and clock. "Offline" shows in a corner while EVAC is unreachable.
gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
util.no_globals()

local json = require "json"
local bold = resource.load_font "font.ttf"
local regular = resource.load_font "font-regular.ttf"
local white = resource.create_colored_texture(1, 1, 1, 1)

local data = {}
local show_clock = true

util.file_watch("data.json", function(raw)
    local ok, parsed = pcall(json.decode, raw)
    if ok and parsed then data = parsed end
end)

util.json_watch("config.json", function(config)
    show_clock = config.clock ~= false
end)

local function hex(colour)
    local r, g, b = colour:match("#(%x%x)(%x%x)(%x%x)")
    if not r then return 0.12, 0.43, 0.92 end
    return tonumber(r, 16) / 255, tonumber(g, 16) / 255, tonumber(b, 16) / 255
end

local function fill(r, g, b, x1, y1, x2, y2)
    white:draw(x1, y1, x2, y2, 1)
    resource.create_colored_texture(r, g, b, 1):draw(x1, y1, x2, y2)
end

-- one line of text, shrunk to fit the width
local function line(font, text, x, y, size, r, g, b, max_width, centre)
    text = tostring(text or "")
    while size > 12 and font:width(text, size) > max_width do size = size * 0.9 end
    local w = font:width(text, size)
    if centre then x = x + (max_width - w) / 2 end
    font:write(x, y, text, size, r, g, b, 1)
    return size
end

-- word-wrapped text block; returns the y below it
local function block(font, text, x, y, size, r, g, b, max_width, centre, max_lines)
    local words, current, lines = {}, "", {}
    for w in tostring(text or ""):gmatch("%S+") do words[#words + 1] = w end
    for _, w in ipairs(words) do
        local candidate = current == "" and w or current .. " " .. w
        if font:width(candidate, size) > max_width and current ~= "" then
            lines[#lines + 1] = current
            current = w
        else
            current = candidate
        end
    end
    if current ~= "" then lines[#lines + 1] = current end
    for i, l in ipairs(lines) do
        if i > (max_lines or 6) then break end
        line(font, l, x, y, size, r, g, b, max_width, centre)
        y = y + size * 1.2
    end
    return y
end

local ARROWS = {ahead = "↑", ahead_right = "↗", right = "→", back_right = "↘", back = "↓", back_left = "↙",
                left = "←", ahead_left = "↖"}

local function draw_evac(e)
    local W, H = WIDTH, HEIGHT
    local danger = e.state == "evacuate"
    local clear = e.state == "all_clear"
    if clear then fill(0.07, 0.45, 0.2, 0, 0, W, H)
    elseif danger then fill(0.75, 0.07, 0.07, 0, 0, W, H)
    else fill(0.85, 0.47, 0.02, 0, 0, W, H) end
    local y = H * 0.1
    if e.drill then
        line(bold, e.drill_text ~= "" and e.drill_text or "DRILL", 0, y, H * 0.05, 1, 1, 1, W, true)
        y = y + H * 0.08
    end
    line(bold, e.label, W * 0.05, y, H * 0.14, 1, 1, 1, W * 0.9, true)
    y = y + H * 0.2
    local arrow = ARROWS[e.arrow or ""]
    if arrow then
        line(bold, arrow, 0, y, H * 0.22, 1, 1, 1, W, true)
        y = y + H * 0.26
    end
    if e.direction and e.direction ~= "" then
        line(bold, e.direction, W * 0.05, y, H * 0.08, 1, 1, 1, W * 0.9, true)
        y = y + H * 0.11
    end
    for _, t in ipairs(e.texts or {}) do
        y = block(regular, t, W * 0.08, y, H * 0.045, 1, 1, 1, W * 0.84, true, 3) + H * 0.01
    end
end

local function draw_banner(o, y, h)
    local r, g, b = hex(o.colour or "#1f6feb")
    fill(r, g, b, 0, y, WIDTH, y + h)
    local title = o.title or ""
    local text = o.text or ""
    local label = title ~= "" and text ~= "" and title .. ": " .. text or title .. text
    line(bold, label, WIDTH * 0.03, y + h * 0.22, h * 0.5, 1, 1, 1, WIDTH * 0.94, false)
end

local function draw_idle()
    gl.clear(0.06, 0.07, 0.09, 1)
    if data.event and data.event ~= "" then
        line(bold, data.event, WIDTH * 0.05, HEIGHT * 0.2, HEIGHT * 0.1, 1, 1, 1, WIDTH * 0.9, true)
    end
    if show_clock then
        local t = os.time() + (data.utc_offset or 0)
        line(bold, os.date("!%H:%M", t), 0, HEIGHT * 0.42, HEIGHT * 0.22, 1, 1, 1, WIDTH, true)
    end
end

local function draw_pairing(p)
    gl.clear(0.06, 0.07, 0.09, 1)
    if p.error then
        line(bold, p.error, WIDTH * 0.05, HEIGHT * 0.4, HEIGHT * 0.06, 1, 0.8, 0.3, WIDTH * 0.9, true)
        line(regular, p.url or "", WIDTH * 0.05, HEIGHT * 0.5, HEIGHT * 0.04, 0.8, 0.8, 0.8, WIDTH * 0.9, true)
        return
    end
    line(regular, "Pair this screen in EVAC: Screens → Pair", WIDTH * 0.05, HEIGHT * 0.25, HEIGHT * 0.05,
         0.8, 0.8, 0.8, WIDTH * 0.9, true)
    line(bold, p.code or "", WIDTH * 0.05, HEIGHT * 0.36, HEIGHT * 0.2, 1, 1, 1, WIDTH * 0.9, true)
    line(regular, p.url or "", WIDTH * 0.05, HEIGHT * 0.66, HEIGHT * 0.035, 0.8, 0.8, 0.8, WIDTH * 0.9, true)
end

function node.render()
    gl.clear(0, 0, 0, 1)
    if data.pairing then return draw_pairing(data.pairing) end
    local e = data.evac
    if e and e ~= json.null and e.takeover then
        draw_evac(e)
    else
        local overlays = data.overlays or {}
        local top = overlays[1]
        if top and top.style == "takeover" then
            fill(0.71, 0.14, 0.09, 0, 0, WIDTH, HEIGHT)
            block(bold, top.title, WIDTH * 0.06, HEIGHT * 0.3, HEIGHT * 0.1, 1, 1, 1, WIDTH * 0.88, true, 4)
        else
            draw_idle()
            local y = HEIGHT * 0.86
            for i, o in ipairs(overlays) do
                if i > 2 then break end
                draw_banner(o, y, HEIGHT * 0.12)
                y = y - HEIGHT * 0.13
            end
        end
        if e and e ~= json.null then
            -- attention / shelter without takeover: a band across the top
            draw_banner({colour = e.state == "all_clear" and "#137333" or "#d97706", title = e.label,
                         text = e.direction or ""}, 0, HEIGHT * 0.12)
        end
    end
    if data.online == false then
        regular:write(WIDTH - 220, HEIGHT - 40, "EVAC offline", 26, 1, 0.8, 0.3, 1)
    end
end
