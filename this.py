return {
  -- Treesitter (Parsers & Syntax Highlighting)
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    opts = {
      ensure_installed = { "lua", "vim", "vimdoc", "c", "cpp", "python" },
      auto_install = true,
      highlight = { enable = true },
    },
    config = function(_, opts)
      require("nvim-treesitter.configs").setup(opts)
    end,
  },

  -- NvimTree (File Explorer)
  {
    "nvim-tree/nvim-tree.lua",
    lazy = false,
    dependencies = {
      "nvim-tree/nvim-web-devicons",
    },
    config = function()
      require("nvim-tree").setup({})
      vim.keymap.set("n", "<C-n>", ":NvimTreeToggle<CR>", { silent = true, desc = "Toggle NvimTree" })
    end,
  },

  -- Twilight (Dim Code Outside Active Scope)
  {
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

      -- Safely enable Twilight automatically after Treesitter attaches
      vim.api.nvim_create_autocmd("FileType", {
        group = vim.api.nvim_create_augroup("AutoTwilight", { clear = true }),
        callback = function(args)
          vim.schedule(function()
            if vim.api.nvim_buf_is_valid(args.buf) and pcall(vim.treesitter.get_parser, args.buf) then
              require("twilight").enable()
            end
          end)
        end,
      })
    end,
  },

  -- Nvim UFO (Treesitter Folding)
  {
    "kevinhwang91/nvim-ufo",
    dependencies = "kevinhwang91/promise-async",
    config = function()
      require("ufo").setup({
        provider_selector = function()
          return { "treesitter", "indent" }
        end,
      })
    end,
  },
}
