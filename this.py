{
  "jake-stewart/multicursor.nvim",
  branch = "1.0",
  config = function()
    local mc = require("multicursor-nvim")
    mc.setup()

    vim.keymap.set({"n", "v"}, "<C-n>", function()
      mc.matchAddCursor(1)
    end)

    vim.keymap.set({"n", "v"}, "<C-p>", function()
      mc.matchAddCursor(-1)
    end)

    vim.keymap.set({"n", "v"}, "<C-Up>", function()
      mc.lineAddCursor(-1)
    end)

    vim.keymap.set({"n", "v"}, "<C-Down>", function()
      mc.lineAddCursor(1)
    end)

    vim.keymap.set("n", "<Esc>", function()
      if not mc.cursorsEnabled() then
        mc.enableCursors()
      elseif mc.hasCursors() then
        mc.clearCursors()
      else
        vim.cmd("nohlsearch")
      end
    end)
  end,
}
