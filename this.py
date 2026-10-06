return {
  "folke/twilight.nvim",
  opts = {
    dimming = { alpha = 0.25 },
    context = 10,
  },
  keys = {
    { "<F4>", "<cmd>Twilight<cr>", desc = "Toggle Twilight Focus" },
  },
  config = function(_, opts)
    require("twilight").setup(opts)

    vim.api.nvim_create_autocmd("BufReadPost", {
      group = vim.api.nvim_create_augroup("AutoTwilight", { clear = true }),
      callback = function()
        -- Only enable if Treesitter has a valid parser for this file
        if pcall(vim.treesitter.get_parser) then
          require("twilight").enable()
        end
      end,
    })
  end,
}
