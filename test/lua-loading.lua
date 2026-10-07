-- A deliberately small model of registration; this does not prove rendering.
local root = arg[1]
local state = { config = {}, layers = {}, windows = {}, animation = {} }
local function merge(target, values)
  for k, value in pairs(values) do
    if type(value) == "table" then
      target[k] = target[k] or {}
      merge(target[k], value)
    else target[k] = value end
  end
end
local hl = {
  config = function(values) merge(state.config, values) end,
  layer_rule = function(rule)
    -- The studied named-rule consumer reuses the object; absent effects survive.
    state.layers[rule.name] = state.layers[rule.name] or {}
    merge(state.layers[rule.name], rule)
  end,
  window_rule = function(rule) state.windows[#state.windows + 1] = rule end,
  animation = function(value) state.animation[value.leaf] = value end,
}
local env = { hl = hl, o = {}, type = type, pairs = pairs }
assert(loadfile(root .. "/test/fixtures/omarchy/window-helper.lua", "t", env))()
local function source()
  assert(loadfile(root .. "/core/hypr/heartchy.lua", "t", env))()
end
package.preload["hypr.heartchy"] = function() source(); return true end
local bootstrap_env = {
  os = { getenv = function(key)
    if key == "HOME" then return "/sandbox/fixture-user" end
    if key == "OMARCHY_PATH" then return "/sandbox/fixture-stock" end
  end },
  package = package, pairs = pairs, ipairs = ipairs, table = table,
}
local function bootstrap()
  assert(loadfile(root .. "/test/fixtures/omarchy/bootstrap.lua", "t", bootstrap_env))()
end
bootstrap()
assert(package.path:find("/sandbox/fixture-user/.config/?.lua", 1, true))
require("hypr.heartchy")
require("hypr.heartchy")
assert(#state.windows == 1, "require within a load must execute once")
assert(state.windows[1].match.tag == "terminal")
assert(state.windows[1].opacity == "1 override 1 override 1 override")
hl.config({ general = { border_size = 3 } })
assert(state.config.general.border_size == 3, "later user scalar must win")

-- The compositor source clears rules during a complete reload; the fixture
-- bootstrap independently clears package.loaded for this module namespace.
state.config, state.layers, state.windows, state.animation = {}, {}, {}, {}
bootstrap()
assert(package.loaded["hypr.heartchy"] == nil)
require("hypr.heartchy")
assert(#state.windows == 1 and state.config.general.border_size == 1)
source()
assert(#state.windows == 2, "direct re-execution accumulates the anonymous rule")
local layer_count = 0
for _ in pairs(state.layers) do layer_count = layer_count + 1 end
assert(layer_count == 1, "the historical named layer rule is reused")
hl.layer_rule({ name = "omarchy-glass-surfaces", blur = false })
assert(state.layers["omarchy-glass-surfaces"].ignore_alpha == 0.10,
  "reusing a name is not whole-object replacement")
print("PASS Lua model: cache, invalidation, scalar precedence, anonymous accumulation, named reuse")
