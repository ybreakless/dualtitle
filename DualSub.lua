--[[
DualTitle Interactive Subtitle Hook & Reader (v4.1) for Unreal Engine 4/5
Deployed to:
  • <SubProject>\Binaries\Win64\ue4ss\Mods\DualSub\Scripts\main.lua
  • <AppRoot>\Binaries\Win64\ue4ss\Mods\DualSub\Scripts\main.lua

Supports BOTH:
  1. Native UE4SS 2.5 / 3.0 Global Lua APIs (`RegisterHook`, `NotifyOnNewObject`,
     `FindFirstOf`, `FindAllOf`, `RegisterKeyBind`, `Key`, `ModifierKey`, `ExecuteInGameThread`)
  2. Static Binary `Game.locres` / `_P.pak` Stacked Subtitles + Live Overlay State Sync

Controls:
  [ALT + F9]  : PAUSE TO READ - Freezes application/cutscenes immediately so you can read.
  [ALT + F10] : PAUSE & HOVER - Freezes application, unlocks mouse, and enables word-hover definitions.
  [SPACE]     : RESUME - Unpauses and returns to active session.
]]

local DualSub = {
    config = {
        enabled = true,
        primary_lang = "en",
        secondary_lang = "de",
        auto_pause_on_dialogue = false,
        word_normal_color = "#FFFFFF",
        word_hover_color = "#FFD700",
        secondary_color = "#CBD5E1",
        tooltip_bg_color = "#0B0F19",
        tooltip_border_color = "#38BDF8",
        line_spacing_px = 14,
        show_background = true
    },

    translations = {},
    dictionary = {},

    initialized = false,
    is_paused = false,
    hover_mode_active = false,
    current_primary_line = "",
    current_secondary_line = "",
    subtitle_widget = nil,
    mod_root_dir = ""
}

local LANG_NAMES = {
    en = "English", de = "Deutsch", fr = "Français", es = "Español",
    ["es-419"] = "Español (Latinoamérica)", it = "Italiano",
    ["pt-BR"] = "Português", pl = "Polski", ru = "Русский",
    ja = "日本語", ko = "한국어", ["zh-Hans"] = "简体中文", ar = "العربية"
}

local function resolve_mod_root()
    if DualSub.mod_root_dir and DualSub.mod_root_dir ~= "" then
        return DualSub.mod_root_dir
    end
    if debug and debug.getinfo then
        local info = debug.getinfo(1, "S")
        if info and info.source then
            local src = info.source:gsub("^@", ""):gsub("\\", "/")
            local parent = src:match("^(.*)/Scripts/[^/]+$") or src:match("^(.*)/scripts/[^/]+$") or src:match("^(.*)/[^/]+$")
            if parent then
                DualSub.mod_root_dir = parent
                return parent
            end
        end
    end
    if ue4ss and ue4ss.GetModsDirectory then
        return ue4ss.GetModsDirectory()
    end
    return "Mods/DualSub"
end

local function simple_json_parse(content)
    if json and json.decode then
        local ok, res = pcall(function() return json.decode(content) end)
        if ok and res then return res end
    end
    local out = {}
    for k, v in content:gmatch('"([^"]+)"%s*:%s*"([^"]*)"') do
        out[k] = v:gsub("\\n", "\n")
    end
    return out
end

local function load_json(path)
    local file = io.open(path, "r")
    if not file then return nil end
    local content = file:read("*all")
    file:close()
    if not content or content == "" then return nil end
    return simple_json_parse(content)
end

local function write_live_subtitle(primary, secondary)
    if not primary or primary == "" then return end
    local root = resolve_mod_root()
    local live_path = root .. "/live_subtitle.json"
    local f = io.open(live_path, "w")
    if f then
        local p_esc = tostring(primary):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ')
        local s_esc = tostring(secondary or ""):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ')
        f:write(string.format('{"primary":"%s","secondary":"%s"}\n', p_esc, s_esc))
        f:close()
    end
end

function DualSub:LoadActiveProfile()
    local root = resolve_mod_root()
    local cfg = load_json(root .. "/dualsub_active_pair.json")
    if cfg then
        if cfg.primary_lang then self.config.primary_lang = cfg.primary_lang end
        if cfg.secondary_lang then self.config.secondary_lang = cfg.secondary_lang end
    end
end

function DualSub:LoadTranslations(primary, secondary)
    local root = resolve_mod_root()
    local pair_name = primary .. "_" .. secondary
    local path = root .. "/translations/" .. pair_name .. ".json"
    local data = load_json(path)
    if data then
        self.translations = data
        print("[DualTitle] Loaded translations for " .. pair_name)
        return true
    end
    local alt_name = secondary .. "_" .. primary
    local alt_data = load_json(root .. "/translations/" .. alt_name .. ".json")
    if alt_data then
        self.translations = alt_data
        return true
    end
    return false
end

function DualSub:LoadDictionary(primary, secondary)
    local root = resolve_mod_root()
    local dict_name = "dict_" .. primary .. "_" .. secondary
    local data = load_json(root .. "/dictionaries/" .. dict_name .. ".json")
    if data then
        self.dictionary = data.words or data
        return true
    end
    local cache_data = load_json(root .. "/dictionaries/famous_dictionary_cache.json")
    if cache_data then
        self.dictionary = cache_data
        return true
    end
    return false
end

function DualSub:LookupWord(raw_word)
    if not raw_word or raw_word == "" then return nil end
    local clean = raw_word:gsub("[%p%c%s]", ""):lower()
    if clean == "" then return nil end

    if self.dictionary[clean] then
        return self.dictionary[clean]
    end
    if clean:sub(-1) == "s" and self.dictionary[clean:sub(1, -2)] then
        return self.dictionary[clean:sub(1, -2)]
    end
    if clean:sub(-2) == "ed" and self.dictionary[clean:sub(1, -3)] then
        return self.dictionary[clean:sub(1, -3)]
    end

    return {
        word = raw_word:gsub("[%p%c]", ""),
        pos = "term",
        source = "DualTitle",
        definition = "Dialogue / Objective term.",
        translation = "(Context: " .. (LANG_NAMES[self.config.secondary_lang] or self.config.secondary_lang) .. ")"
    }
end

function DualSub:GetDualText(table_name, key_or_text)
    if not key_or_text or key_or_text == "" then return nil, nil end

    if type(key_or_text) == "string" and key_or_text:find("\n") then
        local p_line, s_line = key_or_text:match("^([^\r\n]+)\r?\n(.+)$")
        if p_line and s_line then
            return p_line, s_line
        end
    end

    if table_name and self.translations[table_name] and type(self.translations[table_name]) == "table" then
        local entry = self.translations[table_name][key_or_text]
        if entry then
            return self:ParseEntry(entry)
        end
    end

    if self.translations[key_or_text] then
        return self:ParseEntry(self.translations[key_or_text])
    end

    for tname, tbl in pairs(self.translations) do
        if type(tbl) == "table" and tname ~= "metadata" then
            if tbl[key_or_text] then
                return self:ParseEntry(tbl[key_or_text])
            end
            for _k, val in pairs(tbl) do
                local p, s = self:ParseEntry(val)
                if p == key_or_text then
                    return p, s
                end
            end
        end
    end

    return nil, nil
end

function DualSub:ParseEntry(entry)
    if type(entry) == "string" then
        local p, s = entry:match("^(.+)%s*/%s*(.+)$")
        if p and s then
            return p:match("^%s*(.-)%s*$"), s:match("^%s*(.-)%s*$")
        end
        local pn, sn = entry:match("^([^\r\n]+)\r?\n(.+)$")
        if pn and sn then
            return pn, sn
        end
        return entry, ""
    elseif type(entry) == "table" then
        return entry.primary or "", entry.secondary or ""
    end
    return nil, nil
end

function DualSub:GetPlayerController()
    if FindFirstOf then
        local pc = FindFirstOf("PlayerController")
        if pc and pc:IsValid() then return pc end
    end
    if ue4ss and ue4ss.FindClass then
        local GameplayStatics = ue4ss.FindClass("GameplayStatics")
        local world = ue4ss.GetWorld and ue4ss.GetWorld() or nil
        if GameplayStatics and world then
            return GameplayStatics:GetPlayerController(world, 0)
        end
    end
    return nil
end

function DualSub:TogglePauseToRead()
    if self.is_paused then
        self:ResumeGame()
    else
        self:PauseGame(false)
    end
end

function DualSub:TogglePauseToHover()
    if self.is_paused and self.hover_mode_active then
        self:ResumeGame()
    else
        self:PauseGame(true)
    end
end

function DualSub:PauseGame(enable_hover)
    local pc = self:GetPlayerController()
    if pc then
        pcall(function() pc:SetPause(true) end)
        pcall(function()
            pc.bShowMouseCursor = enable_hover and true or false
            pc.bEnableClickEvents = enable_hover and true or false
            pc.bEnableMouseOverEvents = enable_hover and true or false
        end)
    end
    if ue4ss and ue4ss.FindClass then
        local GameplayStatics = ue4ss.FindClass("GameplayStatics")
        local world = ue4ss.GetWorld and ue4ss.GetWorld() or nil
        if GameplayStatics and world then
            pcall(function() GameplayStatics:SetGamePaused(world, true) end)
        end
    end
    self.is_paused = true
    self.hover_mode_active = enable_hover and true or false
    print("[DualTitle] Paused (" .. (enable_hover and "ALT+F10 Hover Dictionary Mode" or "ALT+F9 Read Mode") .. ")")
end

function DualSub:ResumeGame()
    if not self.is_paused then return end
    local pc = self:GetPlayerController()
    if pc then
        pcall(function() pc:SetPause(false) end)
        pcall(function() pc.bShowMouseCursor = false end)
    end
    if ue4ss and ue4ss.FindClass then
        local GameplayStatics = ue4ss.FindClass("GameplayStatics")
        local world = ue4ss.GetWorld and ue4ss.GetWorld() or nil
        if GameplayStatics and world then
            pcall(function() GameplayStatics:SetGamePaused(world, false) end)
        end
    end
    self.is_paused = false
    self.hover_mode_active = false
    print("[DualTitle] Resumed")
end

function DualSub:HookAllGameText()
    if RegisterHook then
        local hook_targets = {
            "/Game/UI/Subtitles/W_SubtitleDisplay.W_SubtitleDisplay_C:DisplaySubtitle",
            "/Game/UI/HUD/WBP_Subtitles.WBP_Subtitles_C:SetSubtitleText",
            "/Game/UI/WBP_SubtitleDisplay.WBP_SubtitleDisplay_C:DisplaySubtitle",
            "/Script/UMG.TextBlock:SetText",
            "/Script/UMG.RichTextBlock:SetText",
        }
        for _, fn_path in ipairs(hook_targets) do
            pcall(function()
                RegisterHook(fn_path, function(self_widget, subtitle_param)
                    if not self.config.enabled then return end
                    local raw_str = ""
                    pcall(function() raw_str = subtitle_param:get():ToString() end)
                    if raw_str ~= "" then
                        local p, s = self:GetDualText(nil, raw_str)
                        if p and s and s ~= "" then
                            self.current_primary_line = p
                            self.current_secondary_line = s
                            write_live_subtitle(p, s)
                        end
                    end
                end)
            end)
        end
    end

    if ue4ss and ue4ss.FindClass then
        local W_SubtitleDisplay = ue4ss.FindClass("W_SubtitleDisplay_C")
        if W_SubtitleDisplay and W_SubtitleDisplay.DisplaySubtitle then
            local original = W_SubtitleDisplay.DisplaySubtitle
            W_SubtitleDisplay.DisplaySubtitle = function(self_widget, subtitle_text, ...)
                if not self.config.enabled then
                    return original(self_widget, subtitle_text, ...)
                end
                local table_name = self_widget.StringTableName and self_widget.StringTableName:ToString() or nil
                local primary, secondary = self:GetDualText(table_name, subtitle_text)
                if primary and secondary and secondary ~= "" then
                    self.current_primary_line = primary
                    self.current_secondary_line = secondary
                    write_live_subtitle(primary, secondary)
                    return original(self_widget, primary .. "\n" .. secondary, ...)
                end
                return original(self_widget, subtitle_text, ...)
            end
        end
    end
end

function DualSub:RegisterKeybinds()
    if RegisterKeyBind and Key then
        pcall(function()
            local alt_mod = ModifierKey and { ModifierKey.ALT } or {}
            RegisterKeyBind(Key.F9, alt_mod, function()
                self:TogglePauseToRead()
            end)
            RegisterKeyBind(Key.F10, alt_mod, function()
                self:TogglePauseToHover()
            end)
            if Key.SPACE then
                RegisterKeyBind(Key.SPACE, function()
                    if self.is_paused then self:ResumeGame() end
                end)
            end
        end)
        print("[DualTitle] Registered UE4SS Keybinds: ALT+F9 (Pause to Read) | ALT+F10 (Pause & Hover)")
        return
    end

    if ue4ss and ue4ss.RegisterKeyBind then
        pcall(function()
            ue4ss.RegisterKeyBind("F9", { ModifierKey and ModifierKey.ALT or 1 }, function()
                self:TogglePauseToRead()
            end)
            ue4ss.RegisterKeyBind("F10", { ModifierKey and ModifierKey.ALT or 1 }, function()
                self:TogglePauseToHover()
            end)
        end)
    end
end

function DualSub:Init()
    print("[DualTitle] Initializing Universal DualTitle v4.1 for Unreal Engine 4/5")
    self:LoadActiveProfile()
    self:LoadTranslations(self.config.primary_lang, self.config.secondary_lang)
    self:LoadDictionary(self.config.primary_lang, self.config.secondary_lang)
    self:HookAllGameText()
    self:RegisterKeybinds()
    print("[DualTitle] Active Pair: " .. self.config.primary_lang .. " + " .. self.config.secondary_lang)
end

if ue4ss and ue4ss.OnGameReady then
    ue4ss.OnGameReady:Add(function()
        DualSub:Init()
    end)
else
    pcall(function()
        DualSub:Init()
    end)
end

return DualSub
