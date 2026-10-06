return {
  "folke/twilight.nvim",
  opts = {
    dimming = { alpha = 0.25 },
    context = 10,
  },
  keys = {
    -- Press F4 to manually toggle Twilight on or off anytime
    { "<F4>", "<cmd>Twilight<cr>", desc = "Toggle Twilight Focus" },
  },
  config = function(_, opts)
    require("twilight").setup(opts)

    -- Enable Twilight automatically when opening any buffer
    vim.api.nvim_create_autocmd("BufReadPost", {
      group = vim.api.nvim_create_augroup("AutoTwilight", { clear = true }),
      callback = function()
        require("twilight").enable()
      end,
    })
  end,
}
