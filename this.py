-- Set mapleader to Space
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- Basic folding settings required for nvim-ufo
vim.o.foldlevel = 99
vim.o.foldlevelstart = 99
vim.o.foldenable = true

-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git",
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

-- Define all your plugins in one table
local plugins = {
  -- Treesitter (Parsers & Highlighting)
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

  -- Twilight (Dim code outside current scope)
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

  -- Nvim UFO (Folding)
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

  -- Import your multicursor file (located at lua/multicursor.lua)
  { import = "multicursor" },
}

-- Initialize Lazy
require("lazy").setup(plugins)
