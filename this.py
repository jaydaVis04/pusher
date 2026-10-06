return {
  "folke/twilight.nvim",
  opts = {
    dimming = { alpha = 0.25 },
    context = 10,
  },
  config = function(_, opts)
    require("twilight").setup(opts)

    -- Enable Twilight automatically when entering any code buffer
    vim.api.nvim_create_autocmd("BufReadPost", {
      group = vim.api.nvim_create_augroup("AutoTwilight", { clear = true }),
      callback = function()
        require("twilight").enable()
      end,
    })
  end,
}
