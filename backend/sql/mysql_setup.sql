-- Run this script in MySQL Workbench using an account allowed to create schemas.
-- Application credentials are configured separately in backend/.env.

CREATE DATABASE IF NOT EXISTS cinematch_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cinematch_test_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE cinematch_db;

CREATE TABLE IF NOT EXISTS movies (
    movie_id VARCHAR(128) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    language VARCHAR(80) NOT NULL,
    release_year INTEGER NOT NULL,
    runtime_minutes INTEGER NULL,
    overview TEXT NOT NULL,
    rating DECIMAL(3, 1) NULL,
    source_url VARCHAR(2048) NOT NULL,
    INDEX idx_movies_title (title),
    INDEX idx_movies_language (language),
    INDEX idx_movies_year (release_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS genres (
    genre_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_genres_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id VARCHAR(128) NOT NULL,
    genre_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    INDEX idx_movie_genres_genre (genre_id),
    CONSTRAINT fk_movie_genres_movie
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id),
    CONSTRAINT fk_movie_genres_genre
        FOREIGN KEY (genre_id) REFERENCES genres(genre_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE cinematch_test_db;

CREATE TABLE IF NOT EXISTS movies (
    movie_id VARCHAR(128) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    language VARCHAR(80) NOT NULL,
    release_year INTEGER NOT NULL,
    runtime_minutes INTEGER NULL,
    overview TEXT NOT NULL,
    rating DECIMAL(3, 1) NULL,
    source_url VARCHAR(2048) NOT NULL,
    INDEX idx_movies_title (title),
    INDEX idx_movies_language (language),
    INDEX idx_movies_year (release_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS genres (
    genre_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_genres_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id VARCHAR(128) NOT NULL,
    genre_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    INDEX idx_movie_genres_genre (genre_id),
    CONSTRAINT fk_movie_genres_movie
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id),
    CONSTRAINT fk_movie_genres_genre
        FOREIGN KEY (genre_id) REFERENCES genres(genre_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
