return {
  "folke/twilight.nvim",
  opts = {
    dimming = { alpha = 0.25 },
    context = 10,
  },
  keys = {
    { "<leader>tw", "<cmd>Twilight<cr>", desc = "Toggle Twilight Focus" },
  },
}

# XD

return {
  "kevinhwang91/nvim-ufo",
  dependencies = "kevinhwang91/promise-async",
  config = function()
    vim.o.foldlevel = 99
    vim.o.foldlevelstart = 99
    vim.o.foldenable = true

    require("ufo").setup()

    -- Custom UFO keybinds using vim.keymap.set
    local keymap = vim.keymap.set
    keymap("n", "zR", require("ufo").openAllFolds, { desc = "Open all folds" })
    keymap("n", "zM", require("ufo").closeAllFolds, { desc = "Close all folds" })
  end,
}
