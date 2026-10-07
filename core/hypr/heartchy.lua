-- Cristal Core: imported from the validated local candidate; see docs/provenance.json.
-- slidevert is a visual preference, not a claim about a current Scrolling bug.

hl.config({
  general = {
    border_size = 1,
    col = {
      active_border = "rgba(b8b8b880)",
      inactive_border = "rgba(88888840)",
    },
  },
  group = {
    col = {
      border_active = "rgba(b8b8b880)",
      border_inactive = "rgba(88888840)",
    },
  },
  decoration = {
    blur = {
      enabled = true,
      size = 6,
      passes = 2,
      vibrancy = 0.0,
      contrast = 0.92,
      brightness = 1.0,
    },
  },
})

hl.layer_rule({
  name = "omarchy-glass-surfaces",
  match = { namespace = "^omarchy-(bar|menu|notifications|keyboard-panel|osd|clipboard|emojis|reminders|polkit|network-qr|network-speedtest|disk-speedtest|image-selector|lock-preview)$" },
  blur = true,
  blur_popups = true,
  ignore_alpha = 0.10,
})

o.window({ tag = "terminal" }, { opacity = "1 override 1 override 1 override" })

hl.animation({
  leaf = "workspaces",
  enabled = true,
  speed = 4,
  bezier = "easeOutQuint",
  style = "slidevert",
})
