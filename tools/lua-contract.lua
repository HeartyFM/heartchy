-- Inspection harness, not a compositor or a runtime dependency of Cristal.
-- The source receives only recording interfaces: no filesystem, processes,
-- environment, package loader, or desktop IPC capabilities.
if _VERSION ~= "Lua 5.4" and _VERSION ~= "Lua 5.5" then
  io.stderr:write("Lua 5.4 or 5.5 required for isolated source inspection\n")
  os.exit(2)
end

local calls = {}
local function record(kind, ...)
  if #calls >= 16 then error("too many declarations") end
  calls[#calls + 1] = { kind = kind, args = { ... } }
end
local function interface(methods)
  return setmetatable({}, {
    __index = function(_, key)
      if methods[key] then return methods[key] end
      error("unsupported interface: " .. tostring(key))
    end,
    __newindex = function() error("interfaces are read-only") end,
    __metatable = false,
  })
end
local environment = interface({
  hl = interface({
    config = function(value) record("config", value) end,
    layer_rule = function(value) record("layer_rule", value) end,
    animation = function(value) record("animation", value) end,
  }),
  o = interface({ window = function(match, rules) record("window", match, rules) end }),
})

local function quote(value)
  return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
    if c == '\\' then return '\\\\' end
    if c == '"' then return '\\"' end
    return string.format("\\u%04x", c:byte())
  end) .. '"'
end
local function encode(value, seen, depth)
  if depth > 12 then error("declaration nesting too deep") end
  local kind = type(value)
  if kind == "string" then return quote(value) end
  if kind == "boolean" then return tostring(value) end
  if kind == "number" and value == value and math.abs(value) ~= math.huge then
    return tostring(value)
  end
  if kind ~= "table" then error("non-data value in declaration") end
  if seen[value] then error("cyclic declaration") end
  seen[value] = true
  local keys, parts, array = {}, {}, #value > 0
  for key in pairs(value) do
    if array then
      if type(key) ~= "number" or key % 1 ~= 0 or key < 1 or key > #value then
        error("mixed array/object declaration")
      end
    elseif type(key) ~= "string" then error("object key must be a string") end
    keys[#keys + 1] = key
  end
  table.sort(keys)
  for _, key in ipairs(keys) do
    local item = encode(value[key], seen, depth + 1)
    parts[#parts + 1] = array and item or (quote(key) .. ":" .. item)
  end
  seen[value] = nil
  return (array and "[" or "{") .. table.concat(parts, ",") .. (array and "]" or "}")
end

local ok, result = pcall(function()
  local chunk, err = load(io.read("*a"), "@core/hypr/heartchy.lua", "t", environment)
  if not chunk then error(err) end
  debug.sethook(function() error("source instruction limit reached") end, "", 100000)
  chunk()
  debug.sethook()
  return encode(calls, {}, 0)
end)
debug.sethook()
if not ok then io.stderr:write(tostring(result) .. "\n"); os.exit(1) end
io.write(result .. "\n")
