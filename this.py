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

return {
  "HampusHauffman/block.nvim",
  config = function()
    require("block").setup({
      percent = 0.8,
      depth = 4,
    })
  end,
}
